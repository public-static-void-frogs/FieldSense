"""Draw a national field sample that is spread over location, crop mix and soil.

Two phases, because soil is only known after a field is looked up in SSURGO:

    # 1. candidates, spread over 1-degree cells x dominant crop group x rotation diversity
    python rule_engine/planner/scripts/sample_fields.py candidates \
        --all data/local/usa_sample_v2/all_fields.csv \
        --cdl data/local/usa_sample/cdl_history_all.parquet \
        --keep data/local/usa_sample/fields.csv --total 60000 \
        --out data/local/usa_sample_v2/candidates.csv
    # ... data/usa_sample/soil.py on candidates.csv ...
    # 2. final sample, thinned so that common soils do not crowd out rare ones
    python rule_engine/planner/scripts/sample_fields.py select \
        --candidates data/local/usa_sample_v2/candidates.csv \
        --soil data/local/usa_sample_v2/soil_candidates.parquet \
        --keep data/local/usa_sample/fields.csv --total 30000 \
        --out data/local/usa_sample_v2/fields.csv

`--all` is the field table (source_id, state_fips, county_fips, county, acres, longitude,
latitude), `--cdl` the CDL history of every CSB field. Fields in `--keep` (the first sample) are
always included. A stratum of N fields gets about c * sqrt(N) fields, so rare places and rare
crop mixes are over-represented compared with a proportional sample: the sample describes the
range of fields, not the average US field. CDL labels are satellite estimates.
"""

import argparse

import duckdb
import numpy as np
import pandas as pd

MIN_ACRES = 10.0
SEED = 20261115
YEARS = range(2018, 2026)

# CDL class -> crop group. Classes not listed are "other" (vegetables, orchards, non-crop).
GROUPS = {
    "corn": [1, 12, 13],
    "soybeans": [5],
    "cotton": [2],
    "rice": [3],
    "sorghum": [4],
    "wheat": [22, 23, 24],
    "small_grain": [21, 25, 27, 28, 29, 30, 205],
    "alfalfa": [36],
    "hay": [37, 58, 59, 60],
    "pasture": [176],
    "fallow": [61],
    "pulses": [42, 51, 52, 53],
    "oilseed": [6, 31, 32, 33, 34, 35, 38],
    "roots": [41, 43, 46],
    "peanuts": [10],
    "double_crop": [26, 225, 226, 228, 236, 237, 238, 239, 240, 241, 254],
}
GROUP_OF = {code: name for name, codes in GROUPS.items() for code in codes}
SOIL_KEYS = ["texture", "drainage", "organic"]


def allocate(sizes: np.ndarray, total: int) -> np.ndarray:
    """About c * sqrt(N) per stratum, at least 1 and at most N, summing to about `total`."""
    low, high = 0.0, float(total)
    for _ in range(60):
        c = (low + high) / 2
        n = np.minimum(sizes, np.maximum(1, np.round(c * np.sqrt(sizes))))
        low, high = (c, high) if n.sum() < total else (low, c)
    return np.minimum(sizes, np.maximum(1, np.round(low * np.sqrt(sizes)))).astype(int)


def candidates(args) -> None:
    con = duckdb.connect()
    cdl = [f"CDL{y}" for y in YEARS]
    mapping = pd.DataFrame({"code": list(GROUP_OF), "grp": list(GROUP_OF.values())})
    con.register("mapping", mapping)
    con.execute(f"""
        CREATE TABLE f AS
        SELECT a.source_id AS CSBID, a.state_fips AS STATEFIPS, a.county_fips AS CNTYFIPS,
               a.county AS CNTY, round(a.acres, 2) AS CSBACRES,
               a.longitude AS centroid_lon, a.latitude AS centroid_lat,
               floor(a.latitude)::INT AS cell_lat, floor(a.longitude)::INT AS cell_lon,
               [{", ".join(f"c.{n}" for n in cdl)}] AS codes
        FROM read_csv('{args.all}', types={{'source_id': 'VARCHAR', 'state_fips': 'VARCHAR',
                                            'county_fips': 'VARCHAR'}}) a
        JOIN '{args.cdl}' c ON c.CSBID = a.source_id
        WHERE a.acres >= {MIN_ACRES}
    """)
    # dominant crop group and the number of distinct crop groups over the eight years
    con.execute("""
        CREATE TABLE g AS
        WITH long AS (
            SELECT CSBID, coalesce(m.grp, 'other') AS grp
            FROM (SELECT CSBID, unnest(codes) AS code FROM f) u
            LEFT JOIN mapping m ON m.code = u.code
        ), counted AS (
            SELECT CSBID, grp, count(*) AS n FROM long GROUP BY ALL
        )
        SELECT CSBID, arg_max(grp, n) AS dominant,
               least(3, count(*) FILTER (WHERE grp <> 'other')) AS diversity
        FROM counted GROUP BY CSBID
    """)
    frame = con.execute("""
        SELECT f.* EXCLUDE (codes), g.dominant, g.diversity
        FROM f JOIN g USING (CSBID)
        WHERE NOT (g.dominant = 'other' AND g.diversity = 0)
    """).df()
    print(f"{len(frame):,} fields of {MIN_ACRES:g} acres or more with a crop in 2018-2025")
    keep = set(pd.read_csv(args.keep, dtype={"CSBID": str})["CSBID"].str.zfill(15))
    rng = np.random.default_rng(SEED)
    frame["stratum"] = frame.groupby(["cell_lat", "cell_lon", "dominant", "diversity"]).ngroup()
    sizes = frame.groupby("stratum").size()
    quota = pd.Series(allocate(sizes.to_numpy(), args.total), index=sizes.index)
    frame["rank"] = rng.random(len(frame))
    frame["rank"] = frame.groupby("stratum")["rank"].rank(method="first")
    chosen = frame[(frame["rank"] <= frame["stratum"].map(quota)) | frame["CSBID"].isin(keep)]
    chosen = chosen.drop(columns=["rank"]).sort_values("CSBID")
    chosen.to_csv(args.out, index=False)
    print(f"{len(sizes):,} strata, wrote {len(chosen):,} candidates "
          f"({chosen['CSBID'].isin(keep).sum():,} from the first sample)")  # fmt: skip
    print(chosen["dominant"].value_counts().to_string())


def soil_class(soil: pd.DataFrame) -> pd.DataFrame:
    sand, clay = soil["sand_pct"], soil["clay_pct"]
    texture = np.select(
        [sand.isna() | clay.isna(), clay >= 35, sand >= 60, clay < 18],
        ["unknown", "clayey", "sandy", "silty_loamy"],
        "loamy",
    )
    drainage = soil["drainage_class"].fillna("unknown").str.lower()
    drainage = np.select(
        [drainage.str.contains("poorly"), drainage.str.contains("excessively"),
         drainage == "unknown"],
        ["poor", "excessive", "unknown"],
        "well",
    )  # fmt: skip
    organic = pd.cut(soil["om_pct"], [-1, 1, 2, 4, 1000], labels=["<1", "1-2", "2-4", ">4"])
    return pd.DataFrame({
        "CSBID": soil["CSBID"].astype(str).str.zfill(15),
        "texture": texture,
        "drainage": drainage,
        "organic": organic.astype(str),
    })  # fmt: skip


def select(args) -> None:
    frame = pd.read_csv(args.candidates, dtype={"CSBID": str, "STATEFIPS": str, "CNTYFIPS": str})
    frame = frame.merge(soil_class(pd.read_parquet(args.soil)), on="CSBID", how="left")
    frame[SOIL_KEYS] = frame[SOIL_KEYS].fillna("unknown")
    keep = set(pd.read_csv(args.keep, dtype={"CSBID": str})["CSBID"].str.zfill(15))
    kept = frame["CSBID"].isin(keep)
    # Weighted draw without replacement: a field's weight falls with the size of its soil class.
    size = frame.groupby(SOIL_KEYS)["CSBID"].transform("size")
    rng = np.random.default_rng(SEED)
    key = rng.random(len(frame)) ** np.sqrt(size.to_numpy())  # Efraimidis-Spirakis, w = N^-1/2
    order = np.argsort(-np.where(kept, 2.0, key))
    chosen = frame.iloc[order[: args.total]].sort_values("CSBID")
    chosen.drop(columns=["stratum"]).to_csv(args.out, index=False)
    print(f"wrote {len(chosen):,} fields ({kept.sum():,} from the first sample)")
    for column in ["dominant", "diversity", *SOIL_KEYS]:
        before = frame[column].value_counts(normalize=True)
        after = chosen[column].value_counts(normalize=True)
        table = pd.DataFrame({"candidates": before, "sample": after}).fillna(0).round(3)
        print(f"\n{column}\n{table.to_string()}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="step", required=True)
    one = sub.add_parser("candidates")
    one.add_argument("--all", required=True)
    one.add_argument("--cdl", required=True)
    two = sub.add_parser("select")
    two.add_argument("--candidates", required=True)
    two.add_argument("--soil", required=True)
    for part in (one, two):
        part.add_argument("--keep", required=True)
        part.add_argument("--total", type=int, required=True)
        part.add_argument("--out", required=True)
    args = parser.parse_args()
    {"candidates": candidates, "select": select}[args.step](args)


if __name__ == "__main__":
    main()
