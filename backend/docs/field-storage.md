# Persistent point fields

`fields` is the shared catalog. Each entry stores required WGS84 `longitude` and
`latitude`, positive `area` in hectares, optional source identity and county
metadata, and supplied attributes. Polygon JSON, estimated extents and map
centroids have been removed. API geometry is always GeoJSON Point in
`[longitude, latitude]` order. `locationKind` is `interior_point` or `user_point`.

`user_fields` links accounts to catalog entries with a composite key. Selection
is private to an account; removing a selection does not delete the shared field.
All field and map endpoints require the existing session cookie.

| Request | Behavior |
| --- | --- |
| `GET /api/v1/fields/catalog` | Browse catalog; default 100, maximum 500, offset pagination |
| `GET /api/v1/fields/catalog/{id}` | Read a catalog point, including source metadata |
| `GET /api/v1/fields` | List the signed-in user's selected fields |
| `POST /api/v1/fields` | Create and select a user point; returns 201 |
| `PUT /api/v1/fields/{id}/selection` | Select an existing field idempotently |
| `DELETE /api/v1/fields/{id}` | Remove only the caller's selection |
| `GET /api/v1/fields/{id}` | Read a selected field; otherwise 404 |

Manual creation requires name, crop, positive area, and a finite coordinate pair.
Only Point geometry is accepted; polygons, extra coordinates and out-of-range
longitude/latitude return 422. Optional positive `parcelId` must be unique (409).

```json
{
  "name": "West Orchard",
  "crop": "Soybeans",
  "area": 12.5,
  "geometry": { "type": "Point", "coordinates": [-93.745, 42.045] }
}
```

Imported fields retain `sourceId`, source year 2025, county/FIPS strings, and all
original GeoJSON properties in `sourceProperties`, including original acreage,
centroid, point method and inner radius where supplied. The point used on the map
is the source geometry, which can differ from its centroid. Acreage is converted
to hectares with factor 0.40468564224. Crop and soil/sensor inputs remain null
unless supplied; the importer does not invent them.

Field weather uses the stored point and the caller's saved time zone. Crop
assessments still require crop and soil inputs; missing inputs return 422.
Unavailable properties/recommendation/strategy resources return 404.

Migration 0005 deliberately replaces the polygon catalog. Accounts, settings and
unrelated dataset records are preserved. Existing selections are saved to
`pending_field_selections`; the importer restores those matching the same stable
source UUID. Unmatched selections remain recoverable there. Old crop/soil samples
are not carried into the new source catalog. Downgrading cannot restore deleted
polygons and is refused explicitly.

See [point import and map performance](field-map-prototype.md) for the import,
restart behavior, bounded map queries and aggregation.
