import type { CatalogFeature } from '../../../types/maps/map.types.ts';

export type ScreenPoint = readonly [number, number];

/** Even-odd containment, including points on the lasso boundary. */
export function isPointInLasso(point: ScreenPoint, polygon: readonly ScreenPoint[]): boolean {
  if (polygon.length < 3 || !point.every(Number.isFinite)) {
    return false;
  }
  const [x, y] = point;
  let inside = false;
  for (let index = 0, previous = polygon.length - 1; index < polygon.length; previous = index++) {
    const [ax, ay] = polygon[previous];
    const [bx, by] = polygon[index];
    const cross = (x - ax) * (by - ay) - (y - ay) * (bx - ax);
    if (
      Math.abs(cross) < 1e-8 &&
      x >= Math.min(ax, bx) &&
      x <= Math.max(ax, bx) &&
      y >= Math.min(ay, by) &&
      y <= Math.max(ay, by)
    ) {
      return true;
    }
    if (ay > y !== by > y && x < ((bx - ax) * (y - ay)) / (by - ay) + ax) {
      inside = !inside;
    }
  }
  return inside;
}

function hasLassoArea(points: readonly ScreenPoint[]): boolean {
  // Unsigned triangle areas reject line/click strokes while allowing a lasso
  // that crosses itself (whose signed polygon area could cancel to zero).
  const [ox, oy] = points[0];
  let area = 0;
  for (let index = 2; index < points.length; index++) {
    const [ax, ay] = points[index - 1];
    const [bx, by] = points[index];
    area += Math.abs((ax - ox) * (by - oy) - (bx - ox) * (ay - oy)) / 2;
  }
  return area >= 16;
}

export function isValidLasso(points: readonly ScreenPoint[]): boolean {
  return points.length >= 3 && hasLassoArea(points);
}

export function getLassoFieldIds(
  features: CatalogFeature[],
  polygon: readonly ScreenPoint[],
  project: (longitude: number, latitude: number) => ScreenPoint,
): string[] {
  if (!isValidLasso(polygon)) {
    return [];
  }
  const west = Math.min(...polygon.map(([x]) => x));
  const east = Math.max(...polygon.map(([x]) => x));
  const north = Math.min(...polygon.map(([, y]) => y));
  const south = Math.max(...polygon.map(([, y]) => y));
  const ids = new Set<string>();
  for (const feature of features) {
    if (feature.properties.kind !== 'field' || feature.id === undefined) {
      continue;
    }
    const [longitude, latitude] = feature.geometry.coordinates;
    const point = project(longitude, latitude);
    if (point[0] < west || point[0] > east || point[1] < north || point[1] > south) {
      continue;
    }
    if (isPointInLasso(point, polygon)) {
      ids.add(String(feature.id));
    }
  }
  return [...ids];
}

export function toggleFieldSelection(selected: ReadonlySet<string>, id: string): Set<string> {
  const next = new Set(selected);
  if (!next.delete(id)) {
    next.add(id);
  }
  return next;
}

export function addFieldSelection(
  selected: ReadonlySet<string>,
  ids: readonly string[],
): Set<string> {
  return new Set([...selected, ...ids]);
}
