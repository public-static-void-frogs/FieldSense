"""Verify the imported map over real local HTTP; remove the temporary test account.

python scripts/benchmark_map.py --base-url http://localhost:8000 --output docs/map-performance.json
"""

import argparse
import json
import math
import secrets
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.core.database import database_engine  # noqa: E402

SCENARIOS = [
    ("national", [-125, 25, -66, 50], 4),
    ("iowa", [-96.7, 40.3, -90.1, 43.6], 7),
    ("county", [-94.2, 41.85, -93.55, 42.25], 11),
    ("farm", [-93.90, 42.02, -93.85, 42.055], 14),
    ("source_sample", [-103.2497, 35.853, -103.247, 35.8555], 16),
    ("outside_coverage", [30.4, 50.4, 30.5, 50.5], 14),
]


def benchmark(base_url, output, samples):
    email = f"map-performance-{uuid4()}@example.com"
    engine = database_engine(Settings().database_url)
    report = dict(
        verifiedAt=datetime.now(timezone.utc).isoformat(),
        target=base_url,
        scope="Real local HTTP, PostgreSQL, full source catalog; no map API mocks",
        scenarios=[],
    )
    with httpx.Client(base_url=base_url, timeout=30) as client:
        try:
            response = client.post(
                "/api/v1/auth/register",
                json=dict(
                    email=email,
                    fullName="Temporary map verification",
                    password=secrets.token_urlsafe(32),
                ),
            )
            response.raise_for_status()
            summary = client.get("/api/v1/maps/summary")
            summary.raise_for_status()
            report["catalog"] = summary.json()
            if report["catalog"]["status"] != "ready":
                raise RuntimeError("Import/index/overview build is not finished.")
            for name, bounds, zoom in SCENARIOS:
                times = []
                maximum_bytes = maximum_features = 0
                data = None
                for _ in range(samples):
                    start = time.perf_counter()
                    response = client.get(
                        "/api/v1/maps/geojson",
                        params=dict(bbox=",".join(map(str, bounds)), zoom=zoom),
                    )
                    elapsed = (time.perf_counter() - start) * 1000
                    response.raise_for_status()
                    data = response.json()
                    if any(feature["geometry"]["type"] != "Point" for feature in data["features"]):
                        raise AssertionError("Map returned non-point geometry")
                    if data["mode"] == "fields" and data["total"] != len(data["features"]):
                        raise AssertionError("Exact point view has inconsistent count")
                    if len(data["features"]) > 600:
                        raise AssertionError("Unbounded map response")
                    times.append(elapsed)
                    maximum_bytes = max(maximum_bytes, len(response.content))
                    maximum_features = max(maximum_features, len(data["features"]))
                ordered = sorted(times)
                row = dict(
                    name=name,
                    bounds=bounds,
                    zoom=zoom,
                    samples=samples,
                    mode=data["mode"],
                    representedFields=data["total"],
                    features=maximum_features,
                    responseBytes=maximum_bytes,
                    p50Ms=round(ordered[len(ordered) // 2], 2),
                    p95Ms=round(ordered[math.ceil(len(ordered) * 0.95) - 1], 2),
                    maxMs=round(max(times), 2),
                )
                report["scenarios"].append(row)
                print(json.dumps(row), flush=True)
            with engine.connect() as connection:
                report["databaseRows"] = connection.scalar(
                    text("SELECT count(*) FROM fields WHERE source_id IS NOT NULL")
                )
                report["overviewCounts"] = [
                    dict(row)
                    for row in connection.execute(
                        text(
                            "SELECT level, sum(count) AS fields, count(*) AS cells FROM field_map_cells GROUP BY level ORDER BY level"
                        )
                    ).mappings()
                ]
                if any(
                    row["fields"] != report["catalog"]["total"] for row in report["overviewCounts"]
                ):
                    raise AssertionError("Aggregate levels do not match the full catalog")
                explain = connection.scalar(
                    text(
                        "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT id, longitude, latitude FROM fields WHERE "
                        "point(longitude,latitude) <@ box(point(-93.90,42.02),point(-93.85,42.055)) LIMIT 601"
                    )
                )
                report["spatialQueryPlan"] = explain
                if "ix_fields_spatial" not in json.dumps(explain):
                    raise AssertionError("Point viewport did not use the spatial index")
                report["fieldStorageBytes"] = connection.scalar(
                    text("SELECT pg_total_relation_size('fields')")
                )
            if report["databaseRows"] != report["catalog"]["total"]:
                raise AssertionError(f"Full archive not verified: {report['databaseRows']} rows")
            output.write_text(json.dumps(report, indent=2, default=str) + "\n")
            print(f"Report saved to {output}", flush=True)
        finally:
            with engine.begin() as connection:
                connection.execute(text("DELETE FROM users WHERE email=:email"), dict(email=email))
            engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--output", type=Path, default=Path("docs/map-performance.json"))
    parser.add_argument("--samples", type=int, default=30)
    options = parser.parse_args()
    benchmark(options.base_url, options.output, options.samples)
