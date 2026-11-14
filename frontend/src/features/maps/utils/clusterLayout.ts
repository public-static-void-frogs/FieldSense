import type { CatalogFeature, MapBounds } from '../../../types/maps/map.types.ts';

export const clusterMarkerSize = 40;
export const clusterMinSpacing = 96;

type PixelPoint = { x: number; y: number };
type PixelViewport = { left: number; top: number; width: number; height: number };
type ClusterMarker = PixelPoint & { count: number; area: number; bounds: MapBounds };

function combine(first: ClusterMarker, second: ClusterMarker): ClusterMarker {
  const count = first.count + second.count;
  return {
    x: (first.x * first.count + second.x * second.count) / count,
    y: (first.y * first.count + second.y * second.count) / count,
    count,
    area: first.area + second.area,
    bounds: [
      Math.min(first.bounds[0], second.bounds[0]),
      Math.min(first.bounds[1], second.bounds[1]),
      Math.max(first.bounds[2], second.bounds[2]),
      Math.max(first.bounds[3], second.bounds[3]),
    ],
  };
}

/** Consolidate bounded API groups in CSS pixels without losing counts or source extents. */
export function layoutMapClusters(
  features: CatalogFeature[],
  project: (longitude: number, latitude: number) => PixelPoint,
  viewport: PixelViewport,
): ClusterMarker[] {
  // World-anchored bins stay stable when panning. Larger screens retain open map space.
  const cellSize = Math.max(160, Math.sqrt((viewport.width * viewport.height) / 40));
  const cells = new Map<string, ClusterMarker>();
  for (const feature of features) {
    if (feature.properties.kind !== 'cluster' || !feature.properties.bounds) {
      continue;
    }
    const [longitude, latitude] = feature.geometry.coordinates;
    const point = project(longitude, latitude);
    const count = feature.properties.count ?? 0;
    if (
      count <= 0 ||
      point.x < viewport.left ||
      point.x > viewport.left + viewport.width ||
      point.y < viewport.top ||
      point.y > viewport.top + viewport.height
    ) {
      continue;
    }
    const item = {
      ...point,
      count,
      area: feature.properties.area,
      bounds: feature.properties.bounds,
    };
    const key = `${Math.floor(point.x / cellSize)},${Math.floor(point.y / cellSize)}`;
    const previous = cells.get(key);
    cells.set(key, previous ? combine(previous, item) : item);
  }
  const margin = clusterMarkerSize / 2 + 12;
  // Leave the scale and wrapped imagery attribution unobstructed on phones.
  const bottomMargin = Math.min(80, Math.max(margin, viewport.height / 2));
  const markers = [...cells.entries()]
    .sort(([first], [second]) => first.localeCompare(second))
    .map(([, item]) => ({
      ...item,
      x: Math.max(
        viewport.left + margin,
        Math.min(viewport.left + viewport.width - margin, item.x),
      ),
      y: Math.max(
        viewport.top + margin,
        Math.min(viewport.top + viewport.height - bottomMargin, item.y),
      ),
    }));
  // Weighted centers in neighboring bins can still meet at an edge. Merge until every
  // remaining pair has enough room, including groups clamped inside the viewport.
  for (let first = 0; first < markers.length; first += 1) {
    for (let second = first + 1; second < markers.length; second += 1) {
      if (
        Math.hypot(markers[first].x - markers[second].x, markers[first].y - markers[second].y) <
        clusterMinSpacing
      ) {
        markers[first] = combine(markers[first], markers[second]);
        markers.splice(second, 1);
        first = -1;
        break;
      }
    }
  }
  return markers;
}
