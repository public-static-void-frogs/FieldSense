"""Import the supplied county point archive with transactional restart checkpoints.

Run after alembic upgrade head. Only an empty catalog or the identical archive
can be loaded. Each county's COPY and checkpoint commit together; reruns resume.
The map returns no incomplete aggregates until the final index/cell build finishes.
"""

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.core.database import database_engine  # noqa: E402
from app.services.maps import rebuild_cells  # noqa: E402

ACRE_HECTARES = 0.40468564224
COLUMNS = (
    "id",
    "crop",
    "area",
    "attributes",
    "created_at",
    "source_id",
    "location_kind",
    "state_fips",
    "county_fips",
    "county",
    "longitude",
    "latitude",
)


def source_record(feature, now, state, county):
    props = feature["properties"]
    source_id = str(props["CSBID"])
    if len(source_id) != 15 or not source_id.isdigit():
        raise ValueError(f"Invalid CSBID {source_id!r}")
    geometry = feature["geometry"]
    if geometry["type"] != "Point" or len(geometry["coordinates"]) != 2:
        raise ValueError(f"Expected point for {source_id}")
    lon, lat = geometry["coordinates"]
    acres = props["CSBACRES"]
    if not all(
        isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
        for v in (lon, lat, acres)
    ):
        raise ValueError(f"Invalid numeric data for {source_id}")
    if not (-180 <= lon <= 180 and -90 <= lat <= 90 and acres > 0):
        raise ValueError(f"Invalid coordinates/area for {source_id}")
    if props["STATEFIPS"] != state or props["CNTYFIPS"] != county:
        raise ValueError(f"County metadata mismatch for {source_id}")
    return (
        str(uuid5(NAMESPACE_URL, f"usda-nass-csb:2025:{source_id}")),
        None,
        acres * ACRE_HECTARES,
        json.dumps({"sourceProperties": props}, allow_nan=False),
        now,
        source_id,
        "interior_point",
        state,
        county,
        props.get("CNTY"),
        lon,
        lat,
    )


def save_progress(connection, metadata):
    connection.execute(
        text(
            "INSERT INTO map_datasets (id, metadata) VALUES ('csb-2025', :metadata) "
            "ON CONFLICT (id) DO UPDATE SET metadata = EXCLUDED.metadata"
        ),
        dict(metadata=json.dumps(metadata)),
    )


def defer_catalog_indexes(connection, metadata):
    """Save exact SQL definitions before dropping indexes that slow random-ID COPY."""
    if "deferredConstraints" in metadata:
        return
    constraints = [
        dict(row)
        for row in connection.execute(
            text("""
        SELECT conrelid::regclass::text AS table_name, conname AS name,
               pg_get_constraintdef(oid) AS definition
        FROM pg_constraint
        WHERE (conrelid = 'fields'::regclass AND contype IN ('p', 'u'))
           OR (confrelid = 'fields'::regclass AND contype = 'f')
        ORDER BY CASE WHEN contype = 'f' THEN 0 WHEN contype = 'p' THEN 1 ELSE 2 END
    """)
        ).mappings()
    ]
    quote = connection.dialect.identifier_preparer.quote
    # FK definitions come first for dropping; restoration runs field keys first.
    for constraint in constraints:
        connection.execute(
            text(
                f"ALTER TABLE {quote(constraint['table_name'])} DROP CONSTRAINT {quote(constraint['name'])}"
            )
        )
    connection.execute(text("DROP INDEX IF EXISTS ix_fields_spatial"))
    metadata["deferredConstraints"] = constraints
    save_progress(connection, metadata)
    connection.commit()


def restore_catalog_indexes(connection, metadata):
    quote = connection.dialect.identifier_preparer.quote
    constraints = metadata.get("deferredConstraints", [])
    for constraint in sorted(constraints, key=lambda c: c["table_name"] != "fields"):
        connection.execute(
            text(
                f"ALTER TABLE {quote(constraint['table_name'])} ADD CONSTRAINT "
                f"{quote(constraint['name'])} {constraint['definition']}"
            )
        )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_fields_spatial ON fields USING gist (point(longitude, latitude))"
        )
    )
    metadata.pop("deferredConstraints", None)
    save_progress(connection, metadata)
    connection.commit()


def import_archive(path):
    # Validate the archive inventory before touching the database.
    with zipfile.ZipFile(path) as archive:
        entries = list(
            csv.DictReader(io.StringIO(archive.read("interior_by_county/index.csv").decode()))
        )
        names = ["interior_by_county/" + row["file"] for row in entries]
        if not entries or len(set(names)) != len(names):
            raise ValueError("Empty or duplicate county manifest")
        if set(names) != {n for n in archive.namelist() if n.endswith(".geojson.gz")}:
            raise ValueError("County manifest does not match archive contents")
        expected = sum(int(row["n_points"]) for row in entries)
        with path.open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        engine = database_engine(Settings().database_url)
        if engine.dialect.name != "postgresql":
            raise ValueError("Full catalog import requires PostgreSQL COPY and GiST")
        with engine.connect() as connection:
            if not connection.scalar(text("SELECT pg_try_advisory_lock(2025, 1107)")):
                raise RuntimeError("Another point import is running")
            metadata = connection.scalar(
                text("SELECT metadata FROM map_datasets WHERE id='csb-2025'")
            )
            if metadata and metadata.get("archiveSha256") != digest:
                raise ValueError("A different dataset is registered; refusing to mix catalogs")
            if not metadata:
                if connection.scalar(text("SELECT count(*) FROM fields WHERE owner_id IS NULL")):
                    raise ValueError(
                        "Catalog is not empty; apply the point replacement migration first"
                    )
                metadata = dict(
                    source="USDA NASS CSB 2025",
                    locationKind="interior_point",
                    total=0,
                    bounds=None,
                    status="importing",
                    archiveSha256=digest,
                    archiveName=path.name,
                    expectedTotal=expected,
                    completedPartitions=[],
                    importedAt=None,
                )
                connection.execute(text("DROP INDEX IF EXISTS ix_fields_spatial"))
                save_progress(connection, metadata)
                connection.commit()
            if metadata["status"] != "ready":
                defer_catalog_indexes(connection, metadata)
                for row, name in zip(entries, names):
                    if name in metadata["completedPartitions"]:
                        continue
                    now = datetime.now(timezone.utc)
                    with (
                        archive.open(name) as compressed,
                        gzip.GzipFile(fileobj=compressed) as source,
                    ):
                        data = json.load(source)
                    features = data["features"]
                    if data["type"] != "FeatureCollection" or len(features) != int(row["n_points"]):
                        raise ValueError(f"County feature count mismatch: {name}")
                    bounds = metadata["bounds"] or [180, 90, -180, -90]
                    raw = connection.connection.driver_connection
                    with raw.cursor() as cursor:
                        with cursor.copy(f"COPY fields ({', '.join(COLUMNS)}) FROM STDIN") as copy:
                            for feature in features:
                                record = source_record(
                                    feature, now, row["STATEFIPS"], row["CNTYFIPS"]
                                )
                                copy.write_row(record)
                                lon, lat = record[-2:]
                                bounds = [
                                    min(bounds[0], lon),
                                    min(bounds[1], lat),
                                    max(bounds[2], lon),
                                    max(bounds[3], lat),
                                ]
                    metadata["total"] += len(features)
                    metadata["bounds"] = bounds
                    metadata["completedPartitions"].append(name)
                    save_progress(connection, metadata)
                    connection.commit()
                    if len(metadata["completedPartitions"]) % 50 == 0:
                        print(
                            f"Counties {len(metadata['completedPartitions'])}/{len(entries)}; points {metadata['total']}",
                            flush=True,
                        )
                actual = connection.scalar(
                    text("SELECT count(*) FROM fields WHERE owner_id IS NULL")
                )
                if metadata["total"] != expected or actual != expected:
                    raise ValueError(
                        f"Catalog count mismatch: expected {expected}, actual {actual}"
                    )
                print("Building point spatial index and aggregate cells", flush=True)
                restore_catalog_indexes(connection, metadata)
                rebuild_cells(connection)
                connection.execute(
                    text(
                        "INSERT INTO user_fields (user_id, field_id, selected_at) "
                        "SELECT p.user_id, p.field_id, p.selected_at FROM pending_field_selections p "
                        "JOIN fields f ON f.id = p.field_id ON CONFLICT DO NOTHING"
                    )
                )
                connection.execute(
                    text(
                        "DELETE FROM pending_field_selections WHERE field_id IN (SELECT id FROM fields)"
                    )
                )
                metadata.update(status="ready", importedAt=datetime.now(timezone.utc).isoformat())
                save_progress(connection, metadata)
                connection.commit()
                connection.execute(text("ANALYZE fields"))
                connection.execute(text("ANALYZE field_map_cells"))
                connection.commit()
            print(
                json.dumps({k: v for k, v in metadata.items() if k != "completedPartitions"}),
                flush=True,
            )
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    import_archive(parser.parse_args().archive)
