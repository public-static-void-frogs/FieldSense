"""Viewport queries with spatial indexes, bounded responses and preaggregated overviews."""

import math

from sqlalchemy import delete, func, select, text

from app.repositories.maps import MapCell, MapDataset

LEVELS = (4, 6, 8, 10, 12)
MAX_FEATURES = 600


def cell_key(longitude, latitude, level):
    size = 1 << level
    return min(size - 1, math.floor((longitude + 180) / 360 * size)), min(
        size - 1, math.floor((latitude + 90) / 180 * size)
    )


def cell_bounds(x, y, level):
    size = 1 << level
    return [
        x / size * 360 - 180,
        y / size * 180 - 90,
        (x + 1) / size * 360 - 180,
        (y + 1) / size * 180 - 90,
    ]


def update_cells(session, field):
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    dialect = session.bind.dialect.name
    insert = pg_insert if dialect == "postgresql" else sqlite_insert
    least = func.least if dialect == "postgresql" else func.min
    greatest = func.greatest if dialect == "postgresql" else func.max
    for level in LEVELS:
        x, y = cell_key(field.longitude, field.latitude, level)
        statement = insert(MapCell).values(
            level=level,
            x=x,
            y=y,
            count=1,
            area=field.area,
            min_lon=field.longitude,
            min_lat=field.latitude,
            max_lon=field.longitude,
            max_lat=field.latitude,
        )
        session.execute(
            statement.on_conflict_do_update(
                index_elements=["level", "x", "y"],
                set_={
                    "count": MapCell.count + 1,
                    "area": MapCell.area + field.area,
                    "min_lon": least(MapCell.min_lon, field.longitude),
                    "min_lat": least(MapCell.min_lat, field.latitude),
                    "max_lon": greatest(MapCell.max_lon, field.longitude),
                    "max_lat": greatest(MapCell.max_lat, field.latitude),
                },
            )
        )

    # Keep the constant-time summary correct after manual additions as well.
    dataset = session.scalar(
        select(MapDataset)
        .where(MapDataset.id == "csb-2025")
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if dataset:
        metadata = dict(dataset.metadata_)
        bounds = metadata["bounds"]
        metadata["total"] += 1
        metadata["bounds"] = [
            min(bounds[0], field.longitude),
            min(bounds[1], field.latitude),
            max(bounds[2], field.longitude),
            max(bounds[3], field.latitude),
        ]
        dataset.metadata_ = metadata


def rebuild_cells(connection):
    if connection.dialect.name == "postgresql":
        connection.execute(text("LOCK TABLE field_map_cells IN EXCLUSIVE MODE"))
    connection.execute(delete(MapCell))
    clamp = "least" if connection.dialect.name == "postgresql" else "min"
    for level in LEVELS:
        size = 1 << level
        connection.execute(
            text(f"""
            INSERT INTO field_map_cells (level, x, y, count, area, min_lon, min_lat, max_lon, max_lat)
            SELECT :level, {clamp}(:edge, CAST(floor((longitude + 180) / 360 * :size) AS INTEGER)),
                   {clamp}(:edge, CAST(floor((latitude + 90) / 180 * :size) AS INTEGER)),
                   count(*), sum(area), min(longitude), min(latitude), max(longitude), max(latitude)
            FROM fields WHERE owner_id IS NULL GROUP BY 2, 3
            """),
            dict(level=level, size=size, edge=size - 1),
        )


def summary(session):
    dataset = session.get(MapDataset, "csb-2025")
    if dataset:
        return dict(dataset.metadata_, defaultCenter=[42.05, -93.87], defaultZoom=11)
    from app.repositories.fields import FieldRecord

    row = session.execute(
        select(
            func.count(),
            func.min(FieldRecord.longitude),
            func.min(FieldRecord.latitude),
            func.max(FieldRecord.longitude),
            func.max(FieldRecord.latitude),
        ).where(FieldRecord.owner_id.is_(None))
    ).one()
    bounds = list(row[1:]) if row[0] else None
    center = [42.05, -93.87]
    if bounds:
        center = [(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2]
    return dict(
        total=row[0],
        bounds=bounds,
        defaultCenter=center,
        defaultZoom=13,
        source="User supplied",
        locationKind="user_point",
        importedAt=None,
    )


def spatial_filter(session, bounds):
    from app.repositories.fields import FieldRecord as F

    west, south, east, north = bounds
    if session.bind.dialect.name == "postgresql":
        return text(
            "point(longitude, latitude) <@ box(point(:west, :south), point(:east, :north))"
        ).bindparams(west=west, south=south, east=east, north=north)
    return F.longitude.between(west, east) & F.latitude.between(south, north)


def cluster_feature(row, viewport_bounds):
    bounds = [row.min_lon, row.min_lat, row.max_lon, row.max_lat]
    west, south, east, north = viewport_bounds
    # A partial edge cell's center may be offscreen; retain a visible zoom target.
    lon_padding = (east - west) * 0.04
    lat_padding = (north - south) * 0.04
    longitude = max(west + lon_padding, min(east - lon_padding, (bounds[0] + bounds[2]) / 2))
    latitude = max(south + lat_padding, min(north - lat_padding, (bounds[1] + bounds[3]) / 2))
    return dict(
        type="Feature",
        id=f"cluster-{row.level}-{row.x}-{row.y}",
        geometry=dict(type="Point", coordinates=[longitude, latitude]),
        properties=dict(kind="cluster", count=row.count, area=round(row.area, 2), bounds=bounds),
    )


def overview(session, bounds, zoom):
    level = min(12, max(4, (int(zoom) + 3) // 2 * 2))
    while True:
        x0, y0 = cell_key(bounds[0], bounds[1], level)
        x1, y1 = cell_key(bounds[2], bounds[3], level)
        rows = list(
            session.scalars(
                select(MapCell)
                .where(MapCell.level == level, MapCell.x.between(x0, x1), MapCell.y.between(y0, y1))
                .limit(MAX_FEATURES + 1)
            )
        )
        if len(rows) <= MAX_FEATURES or level == LEVELS[0]:
            break
        level -= 2
    return dict(
        type="FeatureCollection",
        mode="clusters",
        bounds=list(bounds),
        total=sum(row.count for row in rows),
        features=[cluster_feature(row, bounds) for row in rows],
        limit=MAX_FEATURES,
        source="USDA NASS CSB 2025",
        approximate=True,
    )


def require_ready(session):
    dataset = session.get(MapDataset, "csb-2025")
    if dataset and dataset.metadata_.get("status") != "ready":
        from fastapi import HTTPException

        raise HTTPException(
            status_code=503,
            detail="Field point catalog is being imported",
            headers={"Retry-After": "30"},
        )


def viewport(store, bounds, zoom):
    from app.repositories.fields import FieldRecord as F
    from app.repositories.fields import UserField

    session = store.session
    require_ready(session)
    # Even a forged zoom cannot force a country-wide field scan.
    if zoom < 11 or bounds[2] - bounds[0] > 3 or bounds[3] - bounds[1] > 3:
        return overview(session, bounds, zoom)
    columns = [
        F.id,
        F.parcel_id,
        F.crop,
        F.area,
        F.source_id,
        F.location_kind,
        F.longitude,
        F.latitude,
    ]
    rows = session.execute(
        select(*columns)
        .where(F.owner_id.is_(None), spatial_filter(session, bounds))
        .limit(MAX_FEATURES + 1)
    ).all()
    if len(rows) > MAX_FEATURES:
        return overview(session, bounds, min(zoom, 10))
    ids = [row.id for row in rows]
    selected = (
        set(
            session.scalars(
                select(UserField.field_id).where(
                    UserField.user_id == store.user_id, UserField.field_id.in_(ids)
                )
            )
        )
        if ids
        else set()
    )
    features = []
    for row in rows:
        features.append(
            dict(
                type="Feature",
                id=row.id,
                geometry=dict(type="Point", coordinates=[row.longitude, row.latitude]),
                properties=dict(
                    kind="field",
                    parcelId=row.parcel_id,
                    catalogFieldId=row.id,
                    fieldId=row.id if row.id in selected else None,
                    sourceId=row.source_id,
                    name=row.crop or (f"CSB {row.source_id}" if row.source_id else "Field"),
                    area=row.area,
                    crop=row.crop,
                    locationKind=row.location_kind,
                ),
            )
        )
    return dict(
        type="FeatureCollection",
        mode="fields",
        bounds=list(bounds),
        total=len(rows),
        features=features,
        limit=MAX_FEATURES,
        source="USDA NASS CSB 2025",
        approximate=False,
    )
