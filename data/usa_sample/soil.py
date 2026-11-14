"""SSURGO soil block for every sampled field, from USDA NRCS Soil Data Access.

Two steps, both cached so the script can be rerun: field point -> map unit key (mukey), then
mukey -> properties of the dominant component and its surface horizon. The output columns are
the keys of `field["soil"]` that the rule engine reads (see rule_engine/ssurgo.py).

    python data/usa_sample/soil.py --fields data/local/usa_sample/fields.csv \
        --out data/local/usa_sample/soil.parquet --cache data/local/usa_sample/cache/soil
"""

import argparse
import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from rule_engine.ssurgo import COLUMNS, SDA_URL, SOURCE

POINT_BATCH = 40
MUKEY_BATCH = 150
PROPERTIES = """
SELECT mu.mukey, mu.muname, mu.iacornsr, ma.aws0100wta,
 c.slope_r, c.drainagecl, c.hydgrp, c.nirrcapcl, c.nirrcapscl, c.tfact,
 h.sandtotal_r, h.claytotal_r, h.om_r, h.ph1to1h2o_r, h.caco3_r, h.kwfact
FROM mapunit mu JOIN muaggatt ma ON ma.mukey = mu.mukey
JOIN component c ON c.mukey = mu.mukey AND c.cokey = (
  SELECT TOP 1 c2.cokey FROM component c2 WHERE c2.mukey = mu.mukey
  ORDER BY c2.comppct_r DESC, c2.cokey)
LEFT JOIN chorizon h ON h.cokey = c.cokey AND h.hzdept_r = 0
WHERE mu.mukey IN ({keys})
"""


def sda(query: str, tries: int = 4) -> list[dict]:
    body = json.dumps({"format": "JSON+COLUMNNAME", "query": query}).encode()
    for attempt in range(tries):
        try:
            request = urllib.request.Request(
                SDA_URL, data=body, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(request, timeout=180) as response:
                table = json.load(response).get("Table") or []
            return [dict(zip(table[0], row, strict=True)) for row in table[1:]]
        except Exception as error:  # noqa: BLE001  the service times out now and then
            if attempt == tries - 1:
                print(f"  SDA failed: {error}", flush=True)
                return []
            time.sleep(3 * (attempt + 1))
    return []


def chunks(items, size):
    return [items[i : i + size] for i in range(0, len(items), size)]


def point_mukeys(fields: pd.DataFrame, cache: Path, workers: int) -> pd.DataFrame:
    path = cache / "point_mukey.csv"
    done = (
        pd.read_csv(path, dtype=str)
        if path.exists()
        else pd.DataFrame(columns=["CSBID", "mukey"])
    )
    todo = fields[~fields["CSBID"].isin(done["CSBID"])]
    print(f"points: {len(done):,} cached, {len(todo):,} to fetch", flush=True)

    def fetch(batch):
        query = " UNION ALL ".join(
            f"SELECT '{r.CSBID}' AS id, mukey FROM "
            f"SDA_Get_Mukey_from_intersection_with_WktWgs84('POINT({r.centroid_lon} {r.centroid_lat})')"
            for r in batch.itertuples()
        )
        return sda(query)

    batches = [todo.iloc[i : i + POINT_BATCH] for i in range(0, len(todo), POINT_BATCH)]
    with ThreadPoolExecutor(workers) as pool:
        for index, rows in enumerate(pool.map(fetch, batches), start=1):
            new = pd.DataFrame(rows).rename(columns={"id": "CSBID"})
            if len(new):
                done = pd.concat(
                    [done, new.drop_duplicates("CSBID")], ignore_index=True
                )
            if index % 20 == 0 or index == len(batches):
                done.to_csv(path, index=False)
                print(f"  point batches {index}/{len(batches)}", flush=True)
    return done


def mukey_properties(mukeys: list[str], cache: Path, workers: int) -> pd.DataFrame:
    path = cache / "mukey_properties.csv"
    done = (
        pd.read_csv(path, dtype=str)
        if path.exists()
        else pd.DataFrame(columns=["mukey"])
    )
    todo = sorted(set(mukeys) - set(done["mukey"]))
    print(f"map units: {len(done):,} cached, {len(todo):,} to fetch", flush=True)

    def fetch(batch):
        return sda(PROPERTIES.format(keys=",".join(f"'{int(k)}'" for k in batch)))

    with ThreadPoolExecutor(workers) as pool:
        parts = [
            pd.DataFrame(rows, dtype=str)
            for rows in pool.map(fetch, chunks(todo, MUKEY_BATCH))
        ]
    parts = [p for p in parts if len(p)]
    if parts:
        new = pd.concat(parts, ignore_index=True).drop_duplicates("mukey")
        done = pd.concat([done, new], ignore_index=True)
        done.to_csv(path, index=False)
    return done


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fields", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)
    fields = pd.read_csv(args.fields, dtype={"CSBID": str})
    points = point_mukeys(fields, cache, args.workers)
    props = mukey_properties(
        points["mukey"].dropna().unique().tolist(), cache, args.workers
    )

    out = pd.DataFrame({"mukey": props["mukey"]})
    for column, (key, convert) in COLUMNS.items():
        if column == "mukey" or column not in props:
            continue
        out[key] = [
            convert(v) if isinstance(v, str) and v != "" else None
            for v in props[column]
        ]
    out["source"] = SOURCE
    result = points.merge(out, on="mukey", how="left")
    result.to_parquet(args.out, index=False)
    print(
        f"wrote {args.out}: {len(result):,} of {len(fields):,} fields have a map unit; "
        f"{int(result['slope_pct'].notna().sum()):,} with slope, {int(result['ph'].notna().sum()):,} with pH",
        flush=True,
    )


if __name__ == "__main__":
    main()
