# Section analysis prototype

The toolbar switches between moving the map, drawing with the lasso, and placing
points. In point mode, click to add corners and click the first point or press
Enter to close the outline. Backspace removes the last point. A drawn
zone has a light green fill, keeps its outline and hides selected source points.
Its centered Add button opens the section panel and fits the zone beside it.

Analyze sends the points, closed section geometry and a georeferenced PNG of the
map imagery to `POST /maps/sections/analyze`. Capture excludes UI overlays and
uses the current satellite tiles. The payload includes pixel dimensions, WGS84
image bounds and the image's Web Mercator projection. Capture failures show a
retryable error rather than substituting an empty image.

The green zone pulses while capture and the request run, and Analyze displays a
loading spinner. The backend runs SAM2 on the actual image and point prompts, then runs the trained
TempCNN on 16 clear Sentinel-2 observations downloaded on demand per field.
The results include the observation dates, and fields with insufficient data
are reported as skipped. Crop groups display the names from the model’s training label mapping. See the [API contract](../../backend/docs/section-analysis.md).

On completion the selection outline is replaced by merged crop areas. Nearby masks
of the same crop share one simplified boundary and marker. Click either to toggle
that area, or use the sidebar crop checkbox to toggle all areas of that crop.
Dragging and zooming work over crop icons. The panel summarizes the selected areas,
and Analyze becomes Add areas. Saving merges the selected polygons into the
account’s existing entry for each crop. Saved boundaries appear on field detail
maps.

Cancel section removes its zone/results and restores the original points.
Overlapping selections retain their own points. Pending work is aborted when the
panel is closed or canceled. All section state clears when leaving/reloading the
map. Raw selection remains bounded by the existing viewport response budget.

The preview area is an inexpensive approximation of the drawn outline. After
analysis, displayed areas are geodesic estimates of the actual mask polygons. Masks
may be clipped by the captured image. Analysis requests allow up to five minutes;
other API calls keep their normal timeout. The panel shows progress streamed by
the backend as it segments fields, processes satellite observations and classifies
crops. The backend caches models and encodes
the image once per request. Client cancellation stops backend work between model
batches; an active native operation finishes first.
