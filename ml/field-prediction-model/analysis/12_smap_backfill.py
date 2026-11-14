"""Backfill SMAP L4 surface and root-zone soil moisture for the SMAP cells of the daily field panel, 2015 onward.

The enriched 2025 panel carries 16 SPL4SMGP variables for its EASE-Grid 2.0 9 km cells, but only for
1 Apr-31 Oct 2025. Without an Earthdata login the one keyless copy found is Crop-CASMA (USDA NASS / GMU CSISS):
daily means of the eight 3-hourly SPL4SMGP files for surface (TOP, 0-5 cm) and root-zone (SUB, 0-100 cm) soil
moisture, 2015-03-31 onward, stored on a 9 km CONUS Albers grid (EPSG:5070). No other variable is served.

For each daily layer the script asks Crop-CASMA's WPS for a GeoTIFF clipped to a lon/lat box around the cells,
caches it, and reads one Albers pixel per EASE-2 cell. The Albers copy does not reproduce the EASE-2 values
exactly, so the pixel that stands in for each cell is chosen on 2025 (1 Apr-31 Jul) against the enriched values
and checked on 1 Aug-31 Oct. The choice is pure geometry, so it carries to other years.

SPL4SMGP percentiles are relative to a model climatology for the time of year that Crop-CASMA does not serve.
The script therefore recomputes percentiles per cell from the backfilled record itself (all years, day of year
+-15 days) and reports how they compare with the SPL4SMGP percentiles on 2025.

Usage: python 12_smap_backfill.py --daily path/to/field_daily_2025_enriched/2025 --cache cropcasma_cache \
           --out smap_cellday_2015_2026.parquet
"""
import argparse
import re
import ssl
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import certifi
import duckdb
import numpy as np
import pandas as pd
import pyproj
import rasterio

CTX = ssl.create_default_context(cafile=certifi.where())
HOST = "https://nassgeo.csiss.gmu.edu"
LIST_URL = HOST + "/smap_data/SMAP-9KM-DAILY/SMAP-9KM-DAILY_list.txt"
WPS_URL = HOST + "/smap_service"
# EASE-Grid 2.0 global 9 km (M09), as used by SPL4SMGP
EASE_X0, EASE_Y0, EASE_RES = -17367530.44516138, 7314540.83081304, 9008.055210146
# Crop-CASMA CONUS Albers grid (from the WCS DescribeCoverage of any SMAP-9KM-DAILY layer)
ALB_X0, ALB_Y0, ALB_RES = -2354935.72146259, 3165592.36561653, 9000.0
BANDS = {"TOP": "sm_surface", "SUB": "sm_rootzone"}
TRAIN_END, TEST_START = "2025-07-31", "2025-08-01"
WPS_BODY = (
    '<?xml version="1.0" encoding="UTF-8"?><wps:Execute version="1.0.0" service="WPS" '
    'xmlns="http://www.opengis.net/wps/1.0.0" xmlns:wps="http://www.opengis.net/wps/1.0.0" '
    'xmlns:ows="http://www.opengis.net/ows/1.1"><ows:Identifier>GetFileByAoi</ows:Identifier><wps:DataInputs>'
    "<wps:Input><ows:Identifier>layer</ows:Identifier><wps:Data><wps:LiteralData>{layer}</wps:LiteralData>"
    "</wps:Data></wps:Input><wps:Input><ows:Identifier>aoi</ows:Identifier><wps:Data><wps:LiteralData>{aoi}"
    "</wps:LiteralData></wps:Data></wps:Input></wps:DataInputs><wps:ResponseForm><wps:DataOutput>"
    "<ows:Identifier>outputUrl</ows:Identifier></wps:DataOutput></wps:ResponseForm></wps:Execute>")


def http(url, data=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "field-shift-research",
                                                           "Content-Type": "text/plain; charset=UTF-8"})
    for attempt in range(5):
        try:
            return urllib.request.urlopen(req, timeout=180, context=CTX).read()
        except Exception as e:
            err = e
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"{url}: {err}")


def fetch_layer(layer, aoi, cache):
    band, day = re.match(r"SMAP-9KM-DAILY-(TOP|SUB)_(\d{4})\.\d\d\.\d\d_AVERAGE", layer).groups()
    path = cache / band / day / f"{layer}.tif"
    if path.exists():
        return path
    xml = http(WPS_URL, WPS_BODY.format(layer=layer, aoi=aoi).encode()).decode()
    url = re.search(r"https://[^<\s]+/smap_cache/byAoi/[^<\s]+\.tif", xml)
    if not url:
        raise RuntimeError(f"{layer}: {xml[:300]}")
    tif = http(url.group(0))
    assert tif[:4] in (b"II*\x00", b"MM\x00*"), f"{layer}: not a GeoTIFF"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(tif)
    return path


def read_pixels(path, rows, cols):
    """Values at absolute Albers grid indices; NaN outside the tile or on nodata."""
    with rasterio.open(path) as r:
        a = r.read(1).astype("float64")
        r0 = int(round((ALB_Y0 - r.transform.f) / ALB_RES))
        c0 = int(round((r.transform.c - ALB_X0) / ALB_RES))
        nodata = r.nodata
    a[a == nodata] = np.nan
    rr, cc = rows - r0, cols - c0
    ok = (rr >= 0) & (rr < a.shape[0]) & (cc >= 0) & (cc < a.shape[1])
    out = np.full(rows.shape, np.nan)
    out[ok] = a[rr[ok], cc[ok]]
    return out


def record_percentiles(v, dates, window=15):
    """Percentile of each value among all values of the same cell within +-window days of year (all years)."""
    doy = np.minimum(dates.day_of_year.values, 365)
    out = np.full(v.shape, np.nan)
    for d in range(1, 366):
        tgt = np.where(doy == d)[0]
        if not len(tgt):
            continue
        dist = np.abs(doy - d)
        ref = v[np.minimum(dist, 365 - dist) <= window]           # (n_ref, cells)
        x = v[tgt]                                               # (n_tgt, cells)
        n = np.sum(~np.isnan(ref), axis=0)
        below = np.sum(ref[:, None, :] < x[None, :, :], axis=0)
        ties = np.sum(ref[:, None, :] == x[None, :, :], axis=0)
        out[tgt] = np.where(np.isnan(x), np.nan, 100 * (below + 0.5 * ties) / n)
    return out


def scores(est, ref):
    m = ~np.isnan(est) & ~np.isnan(ref)
    d = est[m] - ref[m]
    return {"n": int(m.sum()), "r": np.corrcoef(est[m], ref[m])[0, 1], "bias": d.mean(), "rmse": np.sqrt((d ** 2).mean()),
            "mae": np.abs(d).mean(), "p95_abs": np.percentile(np.abs(d), 95), "share_within_0.001": np.mean(np.abs(d) < 1e-3)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--daily", required=True, help="folder with the enriched daily panel (*.parquet)")
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True, help="output Parquet: one row per SMAP cell x day")
    ap.add_argument("--start", default="2015-03-31")
    ap.add_argument("--end", default=None, help="last day (default: latest layer on the server)")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    cache, out = Path(args.cache), Path(args.out)
    cache.mkdir(parents=True, exist_ok=True)

    # enriched 2025 values per cell-day (one value per cell-day; any_value is exact)
    ref = duckdb.sql(f"""
        SELECT smap_cell_id, date, any_value(smap_sm_surface) AS sm_surface, any_value(smap_sm_rootzone) AS sm_rootzone,
               any_value(smap_sm_rootzone_pctl) AS sm_rootzone_pctl
        FROM read_parquet('{args.daily}/*.parquet') GROUP BY 1, 2""").df()
    cells = np.sort(ref.smap_cell_id.unique())
    rc = pd.Series(cells).str.extract(r"r(\d+)c(\d+)").astype(int).values
    ex, ey = EASE_X0 + (rc[:, 1] + 0.5) * EASE_RES, EASE_Y0 - (rc[:, 0] + 0.5) * EASE_RES
    ax, ay = pyproj.Transformer.from_crs(6933, 5070, always_xy=True).transform(ex, ey)
    lon, lat = pyproj.Transformer.from_crs(6933, 4326, always_xy=True).transform(ex, ey)
    lo0, lo1, la0, la1 = (np.floor(lon.min() * 10 - 3) / 10, np.ceil(lon.max() * 10 + 3) / 10,
                          np.floor(lat.min() * 10 - 3) / 10, np.ceil(lat.max() * 10 + 3) / 10)
    aoi = ('{"type":"Polygon","coordinates":[[[%s,%s],[%s,%s],[%s,%s],[%s,%s],[%s,%s]]]}'
           % (lo0, la0, lo1, la0, lo1, la1, lo0, la1, lo0, la0))
    print(f"{len(cells)} cells; AOI lon {lo0}..{lo1}, lat {la0}..{la1}")

    listing = cache / "SMAP-9KM-DAILY_list.txt"
    if not listing.exists():
        listing.write_bytes(http(LIST_URL))
    layers = re.findall(r"(SMAP-9KM-DAILY-(?:TOP|SUB)_(\d{4}\.\d\d\.\d\d)_AVERAGE)\.map", listing.read_text())
    days = sorted({pd.Timestamp(d.replace(".", "-")) for _, d in layers})
    end = pd.Timestamp(args.end) if args.end else days[-1]
    want = [(l, pd.Timestamp(d.replace(".", "-"))) for l, d in layers
            if pd.Timestamp(args.start) <= pd.Timestamp(d.replace(".", "-")) <= end]
    print(f"server: {len(days)} days {days[0].date()}..{days[-1].date()}; requesting {len(want)} layers")

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex_:
        paths = list(ex_.map(lambda w: fetch_layer(w[0], aoi, cache), want))
    print(f"tiles ready in {time.time() - t0:.0f} s")

    dates = pd.DatetimeIndex(sorted({d for _, d in want}))
    di = {d: i for i, d in enumerate(dates)}
    tiles = {(layer.split("_")[0].rsplit("-", 1)[1], d): p for (layer, d), p in zip(want, paths)}

    # candidate pixels: the Albers pixel holding the EASE-2 centre and its 5 x 5 neighbourhood
    row0 = np.floor((ALB_Y0 - ay) / ALB_RES).astype(int)
    col0 = np.floor((ax - ALB_X0) / ALB_RES).astype(int)
    offs = [(dr, dc) for dr in range(-2, 3) for dc in range(-2, 3)]
    centre = offs.index((0, 0))

    # choose each cell's pixel on Apr-Jul 2025 (joint RMSE over both layers), check on Aug-Oct
    piv = {v: ref.pivot(index="date", columns="smap_cell_id", values=v).reindex(columns=cells)
           for v in ("sm_surface", "sm_rootzone", "sm_rootzone_pctl")}
    ref_dates = pd.DatetimeIndex(piv["sm_rootzone"].index)
    assert all(d in di for d in ref_dates), "backfill must cover the enriched 2025 dates"
    cand = {b: np.stack([np.stack([read_pixels(tiles[b, d], row0 + dr, col0 + dc) for dr, dc in offs])
                         for d in ref_dates]) for b in BANDS}             # (ref days, offsets, cells)
    train, test = ref_dates <= TRAIN_END, ref_dates >= TEST_START
    sse = np.zeros((len(offs), len(cells)))
    for b, v in BANDS.items():
        sse += np.nanmean((cand[b][train] - piv[v].values[train][:, None, :]) ** 2, axis=0)
    best = np.argmin(np.where(np.isnan(sse), np.inf, sse), axis=0)
    mapping = pd.DataFrame({"smap_cell_id": cells, "alb_row": row0 + np.array([offs[k][0] for k in best]),
                            "alb_col": col0 + np.array([offs[k][1] for k in best]),
                            "shift_rows": [offs[k][0] for k in best], "shift_cols": [offs[k][1] for k in best],
                            "train_rmse_mean": np.sqrt(sse[best, np.arange(len(cells))] / 2)})
    print("pixel shift chosen (rows, cols) -> cells:", mapping.groupby(["shift_rows", "shift_cols"]).size().to_dict())

    vals = {b: np.full((len(dates), len(cells)), np.nan) for b in BANDS}
    for (b, d), p in tiles.items():
        vals[b][di[d]] = read_pixels(p, mapping.alb_row.values, mapping.alb_col.values)
    idx = np.array([di[d] for d in ref_dates])
    rows = []
    for b, v in BANDS.items():
        e = piv[v].values
        for name, sel in (("centre pixel", cand[b][:, centre]), ("chosen pixel", vals[b][idx])):
            for split, m in (("Apr-Jul (fit)", train), ("Aug-Oct (check)", test)):
                s = scores(sel[m].ravel().astype(float), e[m].ravel().astype(float))
                # per-cell temporal correlation (what drought rules and anomalies depend on)
                r_cell = [np.corrcoef(sel[m][:, j], e[m][:, j])[0, 1] for j in range(len(cells))
                          if np.isfinite(sel[m][:, j]).sum() > 10]
                rows.append({"variable": v, "pixel": name, "period": split, **s, "median_cell_r": np.nanmedian(r_cell)})

    pct = {b: record_percentiles(vals[b].astype("float64"), dates) for b in BANDS}
    est = pct["SUB"][idx]
    e = piv["sm_rootzone_pctl"].values
    s = scores(est.ravel(), e.ravel().astype(float))
    r_cell = [np.corrcoef(est[:, j], e[:, j])[0, 1] for j in range(len(cells))]
    rows.append({"variable": "sm_rootzone_pctl (record) vs SPL4SMGP pctl", "pixel": "chosen pixel",
                 "period": "Apr-Oct 2025", **s, "median_cell_r": np.nanmedian(r_cell)})
    m = ~np.isnan(est) & ~np.isnan(e)
    a, b_ = est[m] < 20, e[m] < 20
    print(pd.DataFrame(rows).round(4).to_string(index=False))
    print(f"cell-days below 20th percentile 2025: record {a.mean():.3f}, SPL4SMGP {b_.mean():.3f}, "
          f"agreement {np.mean(a == b_):.3f}, both {np.mean(a & b_):.3f}")

    table = pd.DataFrame({
        "smap_cell_id": np.tile(cells, len(dates)), "date": np.repeat(dates.date, len(cells)),
        "sm_surface": vals["TOP"].astype("float32").ravel(), "sm_rootzone": vals["SUB"].astype("float32").ravel(),
        "sm_surface_pctl_record": pct["TOP"].astype("float32").ravel(),
        "sm_rootzone_pctl_record": pct["SUB"].astype("float32").ravel()})
    out.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(out, compression="zstd", index=False)
    mapping.to_parquet(out.with_name(out.stem + "_cell_map.parquet"), compression="zstd", index=False)
    pd.DataFrame(rows).to_csv(out.with_name(out.stem + "_validation_2025.csv"), index=False)
    print(f"wrote {len(table)} cell-days ({dates[0].date()}..{dates[-1].date()}, "
          f"{int(table.sm_rootzone.isna().sum())} missing root-zone values) to {out}")


if __name__ == "__main__":
    main()
