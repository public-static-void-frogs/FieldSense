"""Soil depletion screening index adapted from the supplied soil_depletion.py."""

import datetime as dt
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from time import monotonic

import httpx
import numpy as np

from app.services.ml.greenness import RASTER_OPTIONS, STAC, _asset_url, _read_window, _scale_offset

logger = logging.getLogger(__name__)

SDA = "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest"
FCC = "https://geo.fcc.gov/api/census/block/find"
NASS = "https://quickstats.nass.usda.gov/api/api_GET/"
WEIGHTS = {"rotation": 0.35, "greenness": 0.30, "soil": 0.20, "county": 0.15}
MIN_COVERAGE = 0.5
SEASON = (
    (6, 15),
    (8, 31),
)  # window in which the yearly peak is searched (Corn Belt); widen for other regions
MAX_CLOUD, MAX_SCENES_YEAR, MIN_SCENES_YEAR, PEAK_Q = 30, 30, 3, 90
FIRST_YEAR_S2 = 2017
RADIUS_M, MIN_VALID_PX, VALID_SCL = 30.0, 3, (4, 5, 6)
TREND_BAD = 2.0  # % per year decline that gives score 1
OM_RANGE, AWS_RANGE = (4.0, 2.0), (25.0, 15.0)  # (healthy, depleted)
MIN_YEARS_TREND = 4
NOT_CROP = re.compile(
    r"fallow|idle|pasture|grass|forest|developed|\bwater\b|wetland|barren|shrub|background|cloud|nonag|hay|alfalfa|clover|ice/snow|aquaculture|^USDA class",
    re.I,
)
NASS_CROP = {
    "corn": ("CORN", "CORN, GRAIN - YIELD, MEASURED IN BU / ACRE"),
    "soybeans": ("SOYBEANS", "SOYBEANS - YIELD, MEASURED IN BU / ACRE"),
}
ASSETS = dict(blue="blue", red="red", nir="nir08", scl="scl")


def _clip01(x):
    return float(min(1.0, max(0.0, x)))


def _years(history):
    return dict(sorted((year, crop) for year, crop in history.items() if crop))


# ------------------------------------------------------------------ rotation
def rotation(hist):
    ys = _years(hist)
    if len(ys) < 2:
        return None, {}
    latest = max(ys)
    latest_crop = ys[latest]
    if NOT_CROP.search(latest_crop):
        return None, {}
    last5 = [crop for year, crop in ys.items() if year >= latest - 4]
    if len(last5) < 2:
        return None, {}
    run = 1
    while ys.get(latest - run) == latest_crop:
        run += 1
    top = max(dict.fromkeys(reversed(last5)), key=last5.count)
    share = last5.count(top) / len(last5)
    sc = 0.6 * _clip01((run - 1) / 3) + 0.4 * _clip01((share - 0.5) / 0.5)
    return sc, {
        "years_same_crop": run,
        "latest_crop": latest_crop,
        "top_crop_5y": top,
        "share_top_crop_5y": round(share, 2),
        "observed_years_5y": len(last5),
    }


# ------------------------------------------------------------------ Sentinel-2 peak greenness
def _search(lat, lng, start, end):
    body = {
        "collections": ["sentinel-2-l2a"],
        "intersects": {"type": "Point", "coordinates": [lng, lat]},
        "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z",
        "limit": 100,
        "query": {"eo:cloud_cover": {"lte": MAX_CLOUD}},
    }
    r = httpx.post(STAC, json=body, timeout=8)
    r.raise_for_status()
    return r.json().get("features", [])


def _scene_ve(item, lat, lng):
    """Mean NDVI and EVI over clear pixels within 30 m of the point on each axis."""
    import rasterio
    from pyproj import Transformer
    from rasterio.enums import Resampling

    assets, props = item["assets"], item["properties"]
    n = int(2 * RADIUS_M / 10)
    with rasterio.Env(**RASTER_OPTIONS):
        with rasterio.open(_asset_url(assets[ASSETS["scl"]])) as dataset:
            x, y = Transformer.from_crs("EPSG:4326", dataset.crs, always_xy=True).transform(
                lng, lat
            )
            bounds = (x - RADIUS_M, y - RADIUS_M, x + RADIUS_M, y + RADIUS_M)
            scl = _read_window(dataset, bounds, (n, n), Resampling.nearest)
        good = np.isin(scl, VALID_SCL)
        if good.sum() < MIN_VALID_PX:
            return None
        refl = {}
        for name in ("blue", "red", "nir"):
            asset = assets[ASSETS[name]]
            resampling = Resampling.bilinear if name == "nir" else Resampling.nearest
            with rasterio.open(_asset_url(asset)) as dataset:
                dn = _read_window(dataset, bounds, (n, n), resampling).astype("float32")
            scale, offset = _scale_offset(asset, props)
            refl[name] = np.where(dn > 0, dn * scale + offset, np.nan)
    for v in refl.values():
        good &= np.isfinite(v)
    if int(good.sum()) < MIN_VALID_PX:
        return None
    b, r, ni = (refl[k][good] for k in ("blue", "red", "nir"))
    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = float(np.nanmean((ni - r) / (ni + r)))
        evi = float(np.nanmean(np.clip(2.5 * (ni - r) / (ni + 6 * r - 7.5 * b + 1), -1, 1)))
    return (ndvi, evi) if np.isfinite(ndvi) and np.isfinite(evi) else None


def yearly_peaks(lat, lng, years, deadline):
    """Return per-year peaks and whether any source error limited the search."""
    peaks, incomplete = {}, False
    years = sorted((y for y in years if FIRST_YEAR_S2 <= y <= dt.date.today().year), reverse=True)
    with ThreadPoolExecutor(max_workers=8) as pool:
        for year in years:
            if monotonic() >= deadline:
                return peaks, True
            start, end = (dt.date(year, *month_day).isoformat() for month_day in SEASON)
            try:
                scenes = _search(lat, lng, start, end)
                # Multiple tiles on the same acquisition date are one observation.
                by_date = {}
                for scene in sorted(scenes, key=lambda item: item["properties"]["eo:cloud_cover"]):
                    by_date.setdefault(scene["properties"]["datetime"][:10], scene)
                items = [by_date[date] for date in sorted(by_date)]
            except (httpx.HTTPError, ValueError, TypeError, KeyError):
                incomplete = True
                continue
            if len(items) > MAX_SCENES_YEAR:
                items = [
                    items[i] for i in np.linspace(0, len(items) - 1, MAX_SCENES_YEAR, dtype=int)
                ]

            def observe(scene):
                if monotonic() >= deadline:
                    return None, True
                try:
                    return _scene_ve(scene, lat, lng), False
                except Exception:
                    return None, True

            values = []
            for value, failed in pool.map(observe, items):
                incomplete |= failed
                if value is not None:
                    values.append(value)
            if len(values) >= MIN_SCENES_YEAR:
                ndvi, evi = np.percentile(values, PEAK_Q, axis=0)
                peaks[year] = {"ndvi": float(ndvi), "evi": float(evi)}
    return peaks, incomplete


def _trend_pct(xs, ys):
    """slope of ys on xs in % of mean(ys) per x unit"""
    xs, ys = np.asarray(xs, float), np.asarray(ys, float)
    if len(xs) < MIN_YEARS_TREND or np.mean(ys) == 0 or np.ptp(xs) == 0:
        return None
    return float(np.polyfit(xs, ys, 1)[0] / abs(np.mean(ys)) * 100.0)


def greenness_part(lat, lng, hist, deadline):
    ys = _years(hist)
    cropyears = [y for y, c in ys.items() if not NOT_CROP.search(c)]
    peaks, incomplete = yearly_peaks(lat, lng, cropyears, deadline)
    metrics = {
        "peak_ndvi": {y: round(p["ndvi"], 3) for y, p in peaks.items()},
        "peak_evi": {y: round(p["evi"], 3) for y, p in peaks.items()},
    }
    trends, weights = [], []
    for crop in sorted({ys[y] for y in peaks}):
        yy = [y for y in peaks if ys[y] == crop]
        t = _trend_pct(yy, [peaks[y]["ndvi"] for y in yy])
        if t is not None:
            trends.append(t)
            weights.append(len(yy))
    score = None
    if trends:
        tr = float(np.average(trends, weights=weights))
        metrics["ndvi_trend_pct_per_yr"] = round(tr, 2)
        score = _clip01(-tr / TREND_BAD)
    note = None
    if incomplete:
        note = "greenness_partial" if peaks else "greenness_unavailable"
    elif score is None:
        note = "greenness_insufficient_years"
    return score, metrics, note


# ------------------------------------------------------------------ soil (SSURGO via Soil Data Access)
def _sda(sql):
    r = httpx.post(SDA, json={"query": sql, "format": "JSON+COLUMNNAME"}, timeout=8)
    r.raise_for_status()
    try:
        t = r.json().get("Table", [])
    except ValueError:
        return []
    return [dict(zip(t[0], row)) for row in t[1:]] if t else []


def _f(x):
    try:
        value = float(x)
        return value if np.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def soil_part(lat, lng):
    mu = _sda(
        f"SELECT TOP 1 mukey FROM SDA_Get_Mukey_from_intersection_with_WktWgs84('POINT({lng} {lat})') ORDER BY mukey"
    )
    if not mu:
        return None, {}, "soil_not_mapped"
    mukey = int(mu[0]["mukey"])
    comp = _sda(
        f"SELECT TOP 1 cokey, compname, slope_r, drainagecl, hydgrp FROM component WHERE mukey = {mukey} AND majcompflag = 'Yes' ORDER BY comppct_r DESC, cokey"
    )
    if not comp:
        return None, {}, "soil_not_mapped"
    cokey = int(comp[0]["cokey"])
    hz = _sda(
        f"SELECT hzdept_r, hzdepb_r, om_r, kffact FROM chorizon WHERE cokey = {cokey} ORDER BY hzdept_r"
    )
    agg = _sda(f"SELECT aws0150wta FROM muaggatt WHERE mukey = {mukey}")
    num, den, kff = 0.0, 0.0, None
    for h in hz:
        t, b, om = _f(h["hzdept_r"]), _f(h["hzdepb_r"]), _f(h["om_r"])
        if kff is None and _f(h["kffact"]) is not None:
            kff = _f(h["kffact"])
        if t is None or b is None or om is None or t >= 30:
            continue
        w = min(b, 30) - t
        if w > 0:
            num += om * w
            den += w
    om30 = num / den if den >= 10 else None
    aws = _f(agg[0]["aws0150wta"]) if agg else None
    slope = _f(comp[0]["slope_r"])
    parts, wts = [], []
    if om30 is not None:
        parts.append(_clip01((OM_RANGE[0] - om30) / (OM_RANGE[0] - OM_RANGE[1])))
        wts.append(0.5)
    if aws is not None:
        parts.append(_clip01((AWS_RANGE[0] - aws) / (AWS_RANGE[0] - AWS_RANGE[1])))
        wts.append(0.25)
    if slope is not None and kff is not None:
        parts.append(_clip01(slope / 10.0) * _clip01(kff / 0.4))
        wts.append(0.25)
    m = {
        "mukey": mukey,
        "soil_component": comp[0]["compname"],
        "drainage_class": comp[0]["drainagecl"],
        "hydrologic_group": comp[0]["hydgrp"],
        "om_pct_0_30cm": None if om30 is None else round(om30, 2),
        "aws0150_cm": aws,
        "slope_pct": slope,
        "kffact": kff,
    }
    return (
        (float(np.average(parts, weights=wts)) if parts else None),
        m,
        None if parts else "soil_insufficient_data",
    )


# ------------------------------------------------------------------ county yield (NASS)
def county_of(lat, lng):
    r = httpx.get(FCC, params={"latitude": lat, "longitude": lng, "format": "json"}, timeout=8)
    r.raise_for_status()
    j = r.json()
    return j["County"]["FIPS"], j["State"]["code"]


def _yield_series(key, crop, state_fips, county_code=None, y0=2010):
    p = {
        "key": key,
        "format": "JSON",
        "source_desc": "SURVEY",
        "commodity_desc": crop,
        "statisticcat_desc": "YIELD",
        "short_desc": NASS_CROP[crop.lower()][1],
        "state_fips_code": state_fips,
        "agg_level_desc": "COUNTY" if county_code else "STATE",
        "year__GE": y0,
    }
    if county_code:
        p["county_code"] = county_code
    r = httpx.get(NASS, params={**p, "domain_desc": "TOTAL", "freq_desc": "ANNUAL"}, timeout=8)
    if r.status_code != 200:
        raise ValueError("NASS yield request failed")
    out = {}
    for d in r.json().get("data", []):
        v = _f(str(d.get("Value", "")).replace(",", ""))
        if v:
            out[int(d["year"])] = v
    return out


def county_part(lat, lng, hist, key):
    if not key:
        return None, {}, "county_not_configured"
    try:
        fips, _ = county_of(lat, lng)
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        return None, {}, "county_unavailable"
    if not isinstance(fips, str) or len(fips) != 5:
        return None, {}, "county_unavailable"
    sf, cc = fips[:2], fips[2:]
    ys = _years(hist)
    ratios = {}
    for name, (com, _) in NASS_CROP.items():
        yrs = [y for y, c in ys.items() if c.lower() == name]
        if not yrs:
            continue
        cy, sy = (
            _yield_series(key, com, sf, cc, min(yrs)),
            _yield_series(key, com, sf, None, min(yrs)),
        )
        for y in yrs:
            if y in cy and y in sy:
                ratios[y] = cy[y] / sy[y]
    if len(ratios) < MIN_YEARS_TREND:
        return None, {"county_fips": fips}, "county_insufficient_years"
    xs = sorted(ratios)
    vals = [ratios[y] for y in xs]
    tr = _trend_pct(xs, vals)
    mean = float(np.mean(vals))
    sc = 0.7 * _clip01(-tr / TREND_BAD) + 0.3 * _clip01((1 - mean) / 0.15)
    return (
        sc,
        {
            "county_fips": fips,
            "county_yield_ratio_mean": round(mean, 3),
            "county_yield_ratio_slope_pct_yr": round(tr, 2),
            "county_yield_years": len(vals),
        },
        None,
    )


# ------------------------------------------------------------------ score
def _level(score):
    if score is None:
        return "unknown"
    if score < 25:
        return "low"
    if score < 50:
        return "moderate"
    if score < 75:
        return "high"
    return "very_high"


def depletion(lat, lng, crop_history, *, nass_key, deadline):
    rotation_score, rotation_metrics = rotation(crop_history)
    components = {"rotation": rotation_score}
    metrics = dict(rotation_metrics)
    notes = [] if rotation_score is not None else ["rotation_insufficient_history"]
    sources = {
        "greenness": lambda: greenness_part(lat, lng, crop_history, deadline),
        "soil": lambda: soil_part(lat, lng),
        "county": lambda: county_part(lat, lng, crop_history, nass_key),
    }
    # Run independent providers together so satellite imagery cannot delay the other reads.
    with ThreadPoolExecutor(max_workers=len(sources)) as pool:
        futures = {name: pool.submit(fetch) for name, fetch in sources.items()}
        for name, future in futures.items():
            try:
                value, observed, note = future.result()
            except Exception as error:
                # Exception messages from HTTP clients can include the NASS API key.
                logger.warning("Soil depletion %s source failed (%s)", name, type(error).__name__)
                value, observed, note = None, {}, f"{name}_unavailable"
            components[name] = value
            metrics.update(observed)
            if note:
                notes.append(note)

    available = {name: value for name, value in components.items() if value is not None}
    coverage = round(sum(WEIGHTS[name] for name in available), 2)
    score = None
    if coverage >= MIN_COVERAGE:
        score = round(
            100 * sum(WEIGHTS[name] * value for name, value in available.items()) / coverage, 1
        )
    drivers = sorted(
        (name for name, value in available.items() if value >= 0.3),
        key=lambda name: -WEIGHTS[name] * available[name],
    )
    return {
        "score": score,
        "level": _level(score),
        "coverage": coverage,
        "components": components,
        "drivers": drivers,
        "metrics": metrics,
        "notes": notes,
    }
