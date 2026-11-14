# Map browser verification — 2026-10-31

Verified against the running local frontend on port 5173 and the production API
on port 8000 with all 15,973,095 source records in PostgreSQL. These are browser
observations, separate from API benchmark and unit-test evidence.

- Desktop viewport: 1440 × 625. Phone viewport: 390 × 844.
- Removed persistent heading/explore, browse list, estimated-bounds note, viewport
  count/status and zoom/recenter button overlays. The scale remains bottom right;
  tile attribution remains visible. Field details open only after clicking a field.
- Clicking a real group at zoom 11 advanced to zoom 13 and replaced groups with
  540 source rectangles. Keyboard `+` advanced to zoom 14, then zoom 15.
- A separate settled zoom-13 view rendered 541 fields using one Canvas with a
  measured layer-update duration of 16.4 ms. A settled panned zoom-15 view rendered
  31 fields using one Canvas, zero group markers and a 2.8 ms layer update.
  These are individual observations, not percentile measurements.
- Dragging preserved the new position; refresh restored
  `/map?lat=42.03548&lon=-93.91993&zoom=15`. Data arrival did not refit the map.
- Clicked source CSBID 351825000000001 in New Mexico. Its preview showed Union
  county, 3.24 ha, unknown crop and the estimated-boundary explanation. Added it
  to My fields, opened its details and returned with browser Back. The original
  viewport and selection persisted. Removed this verification selection and
  confirmed the source field remained available to select.
- Phone field preview for CSBID 191825000218446 fits above the scale, with close
  and selection buttons reachable. Restored the desktop viewport after checking.
- Browser logs showed no application error/warning; one unrelated Chrome
  extension error originated from `chrome-extension://…/js/share-modal.js`.
- Frontend: all 74 tests passed; lint, production build and formatting passed.
  Translation cleanup was additionally checked with all five locale tests.
- Backend: 54 normal tests passed; five opt-in weather simulation tests passed
  separately. Ruff and migration/schema checks passed. The temporary weather
  simulation was stopped after testing.

[API performance evidence](map-performance.json) records actual HTTP percentiles,
response budgets, complete database counts and the spatial index query plan.

![Desktop map](map-prototype-desktop.png)

![Phone field preview](map-prototype-mobile.png)

## Zoomed-out clutter correction

The initial fixed geographic grid could produce hundreds of overlapping 52-pixel
badges. Screen layout now merges nearby source groups into compact 40-pixel badges,
with at least 96 CSS pixels between their computed centers. Merging preserves
counts, area and the combined source bounds used by click-to-zoom. World-anchored
bins reduce movement during panning; navigation and resize events relayout the
markers even while a new viewport request is pending. The bottom 80 pixels remain
available for the scale and attribution. The API and database queries are unchanged.

Verified in Chrome against the full real-data catalog:

- Iowa, zoom 10, 1180 × 681 map: 340 API groups → 34 visible badges;
  minimum measured center distance 98.66 px.
- Iowa, zoom 8: 340 API groups → 32 badges before the bottom-space adjustment.
- Phone, zoom 10, 314 × 844 map: 120 API groups → 10 badges after reserving scale
  space. Markers did not overlap the scale or attribution.
- Clicking consolidated phone groups advanced zoom 10 → 12 → 14; the last view
  rendered 50 real fields using one Canvas.
- Country, zoom 4: 76 API groups → 11 badges.
- All 78 frontend tests passed. Four cluster-layout regressions verify count/area
  and extent preservation, spacing across bin edges, phone density, scale clearance,
  and stable grouping during small pans. Lint, build and formatting checks passed.

![Clear regional groups](map-clusters-desktop.png)

![Clear phone groups](map-clusters-mobile.png)
