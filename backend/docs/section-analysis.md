# Section analysis: SAM2 + TempCNN

`POST /api/v1/maps/sections/analyze` requires the normal session cookie. It runs
real local model inference and never saves fields or modifies the catalog.

## Model preparation

Use Python 3.12 and the backend virtualenv. The official SAM2 source is pinned in
`requirements-ml.txt`. On CPU/macOS, install without the optional CUDA extension:

```sh
.venv/bin/pip install torch==2.15.0 torchvision==0.29.2
SAM2_BUILD_CUDA=0 .venv/bin/pip install --no-build-isolation -r requirements-ml.txt
.venv/bin/python scripts/download_sam2.py
```

On CUDA installations, omit `SAM2_BUILD_CUDA=0` if the optional CUDA extension is
wanted. The runtime defaults to CUDA when available, otherwise CPU; `ML_DEVICE`
can override it. Runtime requests never download weights. SAM2 weights live in
ignored `backend/.cache/models/sam2_hiera_tiny.pt`; TempCNN uses the checked-in
`ml/field-crop-detection-model/weights/tempcnn_best.pth`. Optional
`SAM2_CHECKPOINT` and `TEMPCNN_CHECKPOINT` accept absolute paths.
Missing dependencies/weights, invalid model configuration, or a busy model return
503. Restart the backend after installing dependencies or changing model settings.

## Request and segmentation

- `points`: 1–600 `{ "id": "source-id", "coordinates": [longitude, latitude] }`
  entries, with unique IDs and finite WGS84 positions inside the image bounds.
- `region`: a closed single-ring GeoJSON Polygon in WGS84 longitude/latitude order.
- `image`: `{ "dataUrl": "data:image/png;base64,...", "width": 1024, "height": 768,
  "bounds": [west, south, east, north], "crs": "EPSG:3857" }`.

The browser captures actual satellite imagery for the selected extent, excluding
UI overlays. Image bounds are WGS84 within the Web Mercator latitude limit;
pixels follow EPSG:3857. The maximum is 2048 pixels per dimension and 8 MiB PNG
bytes (browser capture currently caps dimensions at 1536). PNG contents and
sizes are decoded and checked. Invalid requests return 422.

The trained SAM2 tiny model receives the submitted RGB image and independently
segments each positive point prompt, with `multimask_output=False`. Image encoding
runs once per request; prompts are processed in batches of four. Only the mask
component containing the prompt is retained. Actual mask contours, including
holes, are simplified in pixel space and transformed back through Web Mercator
into geographic polygons. Area is geodesic hectares. A missing/degenerate mask
produces a `skippedPoints` entry, never a replacement square. Image-edge masks
are marked `touchesImageEdge`; their extent may be clipped to the captured image.
SAM2 is a general segmenter, so these masks are not validated agricultural parcels.

Models are lazy-loaded and cached per backend process. Each process accepts one
analysis at a time rather than queuing large images behind the mutable predictor.
Inference runs outside the event loop. Client disconnection stops work between
model batches; an executing native model operation must finish first. The browser
uses a five-minute analysis timeout; other API calls keep their ten-second default.

## TempCNN satellite inputs

After SAM2 finds field masks, the backend queries Earth Search for Sentinel-2 L2A
scenes covering each two-degree group of submitted coordinates. It reads windows from the
public raster assets using the supplied script's cloud mask and index formulas.
Reflectance scaling honors Earth Search's applied-offset flag to avoid subtracting
the offset twice. Pixels with nonfinite indices or invalid normalized
ratios are excluded. The model receives the latest 16 distinct clear observation
dates in chronological order, with NDVI, EVI and NDWI in that order. Dates can be
irregular. The search considers up to three pages of 100 recent scenes per group within one year.

Downloads process up to four geographic groups concurrently, with up to four
scenes in flight per group. Fields within the same one-kilometer grid block
share a raster window per band. Each asset opens once per scene read, and a
shared pool of 24 workers reads reflectance bands in parallel after cloud masking.
The samples use a common 10 m grid within the scene. Results are accepted in catalog order to retain
the newest usable observations. Downloads have a four-minute analysis budget. Fields
with incomplete sequences or download failures are reported in `skippedPoints`.
The response includes the dates used for each prediction. The backend never
fills missing dates with fabricated values.

The original TempCNN receives a float32 tensor shaped `(batch, 3, 16)`. Its
training input preparation is unavailable, so the observation cadence used here
has not been validated against the training data. The bundled checkpoint uses the sorted CDL codes from
`data/nasa_hls_greenness_ts/crop_ts.py`: 1 (Corn), 5 (Soybeans), 36 (Alfalfa), and
176 (Grassland/Pasture). The mapping ships alongside the checkpoint. For custom
weights, set `TEMPCNN_CLASSES_PATH` to the matching generated `classes.json`.

## Crop areas

The API returns `cropZones` for map display. It unions masks of each crop in
image pixel space, closes narrow gaps with a six-pixel buffer and erosion, and
simplifies boundaries with a four-pixel tolerance. Disconnected components are
separate zones. Each zone has a crop name, polygon, interior marker location and
area. Individual detections remain in `fields` for existing API consumers.

## Response

The response has `mock: false`, `model: "sam2-tiny+tempcnn"`, `requestId`, `fields`,
`skippedPoints`, and `provenance`. Each field includes:

- `id`, `pointId`, geographic `center`, polygon `geometry`, `areaHa`;
- `classIndex`, `crop`, `cropConfidence`, ordered `cropProbabilities`;
- SAM2 `segmentationConfidence`, and `touchesImageEdge`.

The provenance identifies Sentinel-2 L2A as the crop input source and records the
sequence shape, channel order, device and class mapping source. Each field also
includes `cropObservationDates`. The frontend retains the crop grouping and
deselection controls and reports skipped fields.

## Progress stream

Send `Accept: application/x-ndjson` to the same authenticated endpoint. It streams
one JSON object per line. Progress events include `stage` (segmentation, satellite,
or classification), `completed`, and `total`. Satellite counts represent resolved
observation slots, including slots settled when a field is skipped. The stream
ends with a `result` event containing the normal response, or an `error` event.
Heartbeat events keep the connection active during slow reads. Clients that omit
the streaming header receive the regular JSON response.

### Saving crop areas

`POST /api/v1/fields/crop-areas` accepts selected `{crop, geometry}` polygons.
It unions them with the caller's existing boundary for each crop, recalculates
hectares, and returns the saved entries. Disconnected parts share one
MultiPolygon, and covered additions leave the existing boundary unchanged.
Saved entries are private to the account. Their representative point remains
available to point-based consumers such as weather.
