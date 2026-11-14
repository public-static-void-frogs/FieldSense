# Field point catalog and map

The supplied `interior_by_county-20261107T124704Z-1-001.zip` has 3,087 county
GeoJSON gzip partitions and an index.csv manifest totaling 15,973,095 points.
Source geometry represents an interior field location; it is used directly.
A separate source centroid remains metadata, not the map position. Source
properties, CSB identity, county and leading-zero FIPS codes are retained. Area
is converted from acres to hectares. Crop and soil measurements are not inferred.

## Import

From backend/:

```sh
alembic upgrade head
python scripts/import_field_points.py /path/to/interior_by_county-20261107T124704Z-1-001.zip
```

Migration 0005 removes the old polygon structure and catalog entries. It preserves
accounts/settings and saves selections for restoration by stable source UUID.
It cannot restore deleted polygons on downgrade. The importer requires PostgreSQL
and an empty point catalog or the exact same registered archive SHA-256.

The importer checks the manifest against all county members before loading,
validates feature counts, point geometry, numeric ranges, identity and county
metadata, then COPYs one decompressed county at a time. It does not extract files
or execute source content. A county and its checkpoint commit together; rerunning
the same command resumes without duplicates. An advisory lock prevents concurrent
importers. Primary/source/parcel indexes and dependent foreign keys are deferred during COPY,
with their exact definitions saved transactionally in the checkpoint. They are
rebuilt and validated before the catalog becomes ready. This avoids random UUID
index maintenance on each of sixteen million inserts.

After loading, the importer verifies the exact manifest count, builds the point
GiST index, rebuilds all aggregate levels, restores matching saved selections,
marks the dataset ready and ANALYZEs both tables. While importing, map viewport
reads, catalog browsing, selections and manual field creation return 503 with Retry-After, preventing partial
aggregates and concurrent additions. The summary exposes import status.

## Indexed, bounded queries

`fields` stores required longitude/latitude, not polygon JSON or field extents.
The PostgreSQL GiST expression index is `point(longitude, latitude)`. Close-view
queries use indexed point containment in the requested box and fetch at most
601 rows. At most 600 field points are returned; a dense result switches to
preaggregated clusters without silently truncating fields.

Wide views (over three degrees in either direction) and zooms below 11 read only
`field_map_cells` at levels 4, 6, 8, 10 and 12. Each level preserves field count,
combined hectares and bounds of the represented points. Dense overviews back off
to coarser cells to stay within 600 features. Edge cells include points outside
the exact viewport, so cluster totals are marked approximate. Close-view point
results are exact. A forged high zoom cannot force a nationwide field scan.
New manual fields update all five levels in the same transaction as creation.

Both cluster and field geometry are now Point. Clients distinguish them with
`properties.kind` (`cluster` or `field`), never geometry type. Field properties
include catalogFieldId and only the caller's private fieldId selection marker.

## UI and verification

The catalog uses canvas circle markers for field points and labeled count badges
for clusters. Selecting a point opens the existing source preview and selection
controls. Selected fields use a different color and radius. Overview badges
retain the existing pixel layout and merge counts/areas/bounds without overlaps.
Requests remain debounced and cancellable through React Query. Individual field
maps fit the point at a capped zoom, keep accessible SVG interaction, and use
point terminology in English and Ukrainian.

Run the real local HTTP benchmark after import:

```sh
python scripts/benchmark_map.py --output docs/point-map-performance.json
```

It creates/removes a temporary account, measures national/state/county/farm and
empty views, checks the rendering cap, captures the point index EXPLAIN plan,
and records database row and aggregate counts. Older map-performance reports
refer to the retired rectangle catalog and do not establish point performance.
