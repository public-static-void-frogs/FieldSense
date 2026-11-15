import type { Position } from 'geojson';
import type { Field } from '../../../types/fields/field.types.ts';
import { isPointInLasso, type ScreenPoint } from './lassoSelection.ts';

export function getSavedFieldCoverage(fields: Field[] | undefined) {
  return (fields ?? []).flatMap(({ boundary }) =>
    (boundary?.coordinates ?? [])
      .filter((part) => part[0]?.length)
      .map(([outer, ...holes]) => {
        let west = Infinity;
        let east = -Infinity;
        let south = Infinity;
        let north = -Infinity;
        const ring = outer.map(([longitude, latitude]): ScreenPoint => {
          west = Math.min(west, longitude);
          east = Math.max(east, longitude);
          south = Math.min(south, latitude);
          north = Math.max(north, latitude);
          return [longitude, latitude];
        });

        return {
          west,
          east,
          south,
          north,
          ring,
          holes: holes.map((hole) => hole.map(([lon, lat]): ScreenPoint => [lon, lat])),
        };
      }),
  );
}

export function isCoveredBySavedField(
  [longitude, latitude]: Position,
  coverage: ReturnType<typeof getSavedFieldCoverage>,
): boolean {
  const point: ScreenPoint = [longitude, latitude];

  return coverage.some(
    ({ west, east, south, north, ring, holes }) =>
      longitude >= west &&
      longitude <= east &&
      latitude >= south &&
      latitude <= north &&
      isPointInLasso(point, ring) &&
      !holes.some((hole) => isPointInLasso(point, hole)),
  );
}
