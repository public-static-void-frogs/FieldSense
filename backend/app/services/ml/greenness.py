"""Sentinel-2 time series adapted from the supplied greenness_vector.py."""

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from math import floor
from time import monotonic
from urllib.parse import urlsplit

import numpy as np

STAC = "https://earth-search.aws.element84.com/v1/search"
LOOKBACK_DAYS = 365
SEQUENCE_LENGTH = 16
SCENE_WINDOW = 4
GRID_M = 10
BLOCK_PIXELS = 100  # Share windows within 1 km blocks without reading large sparse areas.
RASTER_OPTIONS = {
    "GDAL_HTTP_TIMEOUT": "8",
    "GDAL_HTTP_MAX_RETRY": "0",
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
}
MAX_CLOUD = 70  # scene-level eo:cloud_cover filter, %
RADIUS_M = 30.0  # half side of the square read around the point (30 m -> 6x6 px at 10 m)
MIN_VALID_PX = 3
VALID_SCL = (4, 5, 6)
ASSETS = dict(
    blue="blue", red="red", nir="nir08", swir="swir16", scl="scl"
)  # nir08 = B8A, swir16 = B11


def _search(points, start, end, check_budget):
    import requests

    longitudes, latitudes = zip(*points)
    body = {
        "collections": ["sentinel-2-l2a"],
        "bbox": [
            max(-180, min(longitudes) - 1e-4),
            max(-90, min(latitudes) - 1e-4),
            min(180, max(longitudes) + 1e-4),
            min(90, max(latitudes) + 1e-4),
        ],
        "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z",
        "limit": 100,
        "query": {"eo:cloud_cover": {"lte": MAX_CLOUD}},
        "sortby": [{"field": "properties.datetime", "direction": "desc"}],
    }
    items = []
    with requests.Session() as session:
        for _ in range(3):
            check_budget()
            response = session.post(STAC, json=body, timeout=(5, 12))
            response.raise_for_status()
            page = response.json()
            items.extend(page.get("features", []))
            next_page = next(
                (link for link in page.get("links", []) if link["rel"] == "next"), None
            )
            if not next_page or not isinstance(next_page.get("body"), dict):
                break
            body = {**body, **next_page["body"]}
    return items


def _scale_offset(asset, props):
    band = (asset.get("raster:bands") or [{}])[0]
    scale = float(band.get("scale", 1e-4))
    # Earth Search can advertise a band offset even after applying it to the COG.
    if props.get("earthsearch:boa_offset_applied") is True:
        return scale, 0.0
    if "offset" in band:
        return scale, float(band["offset"])
    try:
        baseline = float(props.get("s2:processing_baseline", 0))
    except (TypeError, ValueError):
        baseline = 0
    return scale, (-1000 * scale if baseline >= 4 else 0.0)


def _read_window(dataset, bounds, shape, resampling):
    from rasterio.windows import from_bounds

    win = from_bounds(*bounds, dataset.transform)
    inside = (
        win.col_off >= 0
        and win.row_off >= 0
        and win.col_off + win.width <= dataset.width + 1e-6
        and win.row_off + win.height <= dataset.height + 1e-6
    )
    return dataset.read(
        1, window=win, out_shape=shape, resampling=resampling, boundless=not inside, fill_value=0
    )


def _asset_url(asset):
    href = asset["href"]
    url = urlsplit(href)
    if url.scheme != "https" or url.netloc != "sentinel-cogs.s3.us-west-2.amazonaws.com":
        raise ValueError("Unexpected Sentinel-2 asset URL")
    return href


def _scene_vectors(item, points, check_budget, band_pool):
    import rasterio
    from pyproj import Transformer
    from rasterio.enums import Resampling

    assets, props = item["assets"], item["properties"]
    half = int(RADIUS_M / GRID_M)
    blocks = defaultdict(list)
    windows = []
    with rasterio.Env(**RASTER_OPTIONS), rasterio.open(_asset_url(assets[ASSETS["scl"]])) as scl:
        origin_x, origin_y = scl.transform.c, scl.transform.f
        transform = Transformer.from_crs("EPSG:4326", scl.crs, always_xy=True)
        xs, ys = transform.transform(*zip(*points))
        for point, x, y in zip(points, xs, ys):
            col = floor((x - origin_x) / GRID_M)
            row = floor((origin_y - y) / GRID_M)
            blocks[row // BLOCK_PIXELS, col // BLOCK_PIXELS].append((point, row, col))

        for cells in blocks.values():
            check_budget()
            rows = [row for _, row, _ in cells]
            cols = [col for _, _, col in cells]
            r0, r1 = min(rows) - half, max(rows) + half
            c0, c1 = min(cols) - half, max(cols) + half
            bounds = (
                origin_x + c0 * GRID_M,
                origin_y - r1 * GRID_M,
                origin_x + c1 * GRID_M,
                origin_y - r0 * GRID_M,
            )
            shape = (r1 - r0, c1 - c0)
            try:
                clear = np.isin(_read_window(scl, bounds, shape, Resampling.nearest), VALID_SCL)
            except rasterio.errors.RasterioError:
                continue
            samples = []
            for point, row, col in cells:
                sample = (
                    slice(row - half - r0, row + half - r0),
                    slice(col - half - c0, col + half - c0),
                )
                if clear[sample].sum() >= MIN_VALID_PX:
                    samples.append((point, sample))
            if samples:
                windows.append((bounds, shape, clear, samples))

    if not windows:
        return {}

    def read_band(band):
        check_budget()
        asset = assets[ASSETS[band]]
        scale, offset = _scale_offset(asset, props)
        resampling = Resampling.bilinear if band in ("nir", "swir") else Resampling.nearest
        result = []
        with rasterio.Env(**RASTER_OPTIONS), rasterio.open(_asset_url(asset)) as dataset:
            for bounds, shape, _, _ in windows:
                check_budget()
                try:
                    result.append(_read_window(dataset, bounds, shape, resampling))
                except rasterio.errors.RasterioError:
                    result.append(None)
        return (scale, offset), result

    scales, bands = zip(*band_pool.map(read_band, ("blue", "red", "nir", "swir")))
    result = {}
    for (_, _, clear, samples), digital_numbers in zip(windows, zip(*bands)):
        if any(band is None for band in digital_numbers):
            continue
        valid = clear & (np.asarray(digital_numbers) > 0).all(axis=0)
        for point, sample in samples:
            vector = _indices(
                [
                    band[sample][valid[sample]].astype("float32") * scale + offset
                    for band, (scale, offset) in zip(digital_numbers, scales)
                ]
            )
            if vector is not None:
                result[point] = vector
    return result


def _indices(reflectance):
    blue, red, nir, swir = reflectance
    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = (nir - red) / (nir + red)
        evi = 2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1)
        ndwi = (nir - swir) / (nir + swir)
    indices = np.stack((ndvi, evi, ndwi), axis=1)
    # Negative corrected reflectance can make normalized ratios exceed their physical range.
    valid = (
        np.isfinite(indices).all(axis=1)
        & (nir + red > 0)
        & (nir + swir > 0)
        & (np.abs(ndvi) <= 1)
        & (np.abs(ndwi) <= 1)
    )
    indices = indices[valid]
    if len(indices) < MIN_VALID_PX:
        return None
    indices[:, 1] = np.clip(indices[:, 1], -1, 1)
    return indices.mean(axis=0)


class GreennessUnavailable(Exception):
    pass


def greenness_sequences(points, deadline, check_cancelled, on_progress=None):
    """Load sixteen distinct clear dates per (longitude, latitude) coordinate."""
    cells = defaultdict(list)
    for lon, lat in dict.fromkeys(points):
        cells[floor(lon / 2), floor(lat / 2)].append((lon, lat))

    with (
        ThreadPoolExecutor(max_workers=24) as bands,
        ThreadPoolExecutor(max_workers=4) as groups,
    ):
        jobs = [
            groups.submit(_load_cell, cell, deadline, check_cancelled, bands, on_progress)
            for cell in cells.values()
        ]
        return {
            point: result for job in as_completed(jobs) for point, result in job.result().items()
        }


def _load_cell(points, deadline, check_cancelled, bands, on_progress):
    import rasterio
    import requests

    def check_budget():
        check_cancelled()
        if monotonic() >= deadline:
            raise GreennessUnavailable("Satellite download time limit reached")

    def advance(point, count):
        if on_progress is not None:
            on_progress(point, count)

    observations = {point: {} for point in points}
    results = {}
    read_failures = defaultdict(int)
    reason = None
    try:
        check_budget()
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=LOOKBACK_DAYS)
        items = sorted(
            _search(points, start.isoformat(), end.isoformat(), check_budget),
            key=lambda item: item["properties"]["datetime"],
            reverse=True,
        )

        def read_scene(item, candidates):
            check_budget()
            try:
                return _scene_vectors(item, candidates, check_budget, bands)
            except (rasterio.errors.RasterioError, OSError, KeyError, ValueError):
                return None

        with ThreadPoolExecutor(max_workers=SCENE_WINDOW) as scenes:
            pending = {}
            catalog = iter(items)

            def refill():
                while len(pending) < SCENE_WINDOW and observations:
                    item = next(catalog, None)
                    if item is None:
                        break
                    day = item["properties"]["datetime"][:10]
                    west, south, east, north = item["bbox"]
                    candidates = [
                        (lon, lat)
                        for (lon, lat), dates in observations.items()
                        if day not in dates and west <= lon <= east and south <= lat <= north
                    ]
                    if candidates:
                        pending[scenes.submit(read_scene, item, candidates)] = (day, candidates)

            try:
                refill()
                # Commit newest first, regardless of which download completes first.
                while pending and observations:
                    check_budget()
                    future = next(iter(pending))
                    day, candidates = pending.pop(future)
                    vectors = future.result()
                    if vectors is None:
                        for point in candidates:
                            read_failures[point] += 1
                    else:
                        for point, vector in vectors.items():
                            days = observations.get(point)
                            if days is None or day in days:
                                continue
                            days[day] = vector
                            advance(point, 1)
                            if len(days) == SEQUENCE_LENGTH:
                                dates = sorted(days)
                                results[point] = dates, np.stack([days[date] for date in dates])
                                del observations[point]
                    refill()
            finally:
                for future in pending:
                    future.cancel()
    except GreennessUnavailable as error:
        reason = str(error)
    except (requests.RequestException, ValueError):
        reason = "Satellite catalog unavailable"

    for point, days in observations.items():
        detail = reason or f"Only {len(days)} of 16 clear satellite observation dates available"
        if read_failures[point]:
            detail += f" ({read_failures[point]} scene reads failed)"
        results[point] = detail
        advance(point, SEQUENCE_LENGTH - len(days))
    return results
