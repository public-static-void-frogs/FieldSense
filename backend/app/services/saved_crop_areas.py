"""Persist one dissolved boundary per account and crop."""

from collections import defaultdict

from fastapi import HTTPException
from pyproj import Geod
from shapely import MultiPolygon, Polygon, get_parts, union_all
from shapely.geometry import mapping, shape
from shapely.geometry.polygon import orient
from sqlalchemy import delete, select, update

from app.repositories.fields import FieldRecord, UserField, field_view
from app.repositories.users import User

GEOD = Geod(ellps="WGS84")


def save_crop_areas(store, areas):
    by_crop = defaultdict(list)
    for area in areas:
        polygon = Polygon(area.geometry.coordinates[0], area.geometry.coordinates[1:])
        if not polygon.is_valid or polygon.is_empty or polygon.bounds[2] - polygon.bounds[0] >= 180:
            raise HTTPException(422, "Invalid crop area boundary")
        by_crop[area.crop].append(polygon)

    session = store.session
    # Serialize additions even when the first request for a crop has no field row to lock.
    if session.get_bind().dialect.name == "sqlite":
        session.execute(update(User).where(User.id == store.user_id).values(id=User.id))
    else:
        session.execute(
            select(User.id).where(User.id == store.user_id).with_for_update()
        ).scalar_one()

    saved = []
    for crop, additions in sorted(by_crop.items()):
        row = session.scalar(
            select(FieldRecord)
            .where(FieldRecord.owner_id == store.user_id, FieldRecord.crop == crop)
            .with_for_update()
        )
        if row is not None:
            previous = shape(row.boundary)
            if all(previous.covers(polygon) for polygon in additions):
                saved.append(row)
                continue
            additions.append(previous)

        polygons = [
            orient(part, sign=1)
            for part in get_parts(union_all(additions).simplify(0, preserve_topology=True))
        ]
        boundary = MultiPolygon(polygons)
        hectares = sum(abs(GEOD.geometry_area_perimeter(part)[0]) for part in polygons) / 10_000
        if hectares <= 0:
            raise HTTPException(422, "Crop boundary must enclose a positive area")
        point = boundary.representative_point()

        if row is None:
            row = FieldRecord(
                owner_id=store.user_id,
                crop=crop,
                location_kind="crop_area",
                attributes={},
                longitude=point.x,
                latitude=point.y,
                area=hectares,
            )
            session.add(row)
            session.flush()
            session.add(UserField(user_id=store.user_id, field_id=row.id))
        row.boundary = mapping(boundary)
        row.area = hectares
        row.longitude, row.latitude = point.x, point.y
        # Legacy point selections have no boundary to union. Keep the shared source rows.
        session.execute(
            delete(UserField).where(
                UserField.user_id == store.user_id,
                UserField.field_id.in_(
                    select(FieldRecord.id).where(
                        FieldRecord.owner_id.is_(None), FieldRecord.crop == crop
                    )
                ),
            )
        )
        saved.append(row)

    session.commit()
    return [field_view(row) for row in saved]
