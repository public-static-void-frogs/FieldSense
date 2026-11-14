import type { Feature } from 'geojson';
import { isGuid } from '../../../utils/ids.ts';
import type { FieldGeoJson } from '../../../types/maps/map.types.ts';

/** Geographic bounds in Leaflet's [latitude, longitude] order. */
export function getGeoJsonBounds(
  geojson: FieldGeoJson,
): [[number, number], [number, number]] | null {
  let west = Infinity;
  let south = Infinity;
  let east = -Infinity;
  let north = -Infinity;
  for (const feature of geojson.features) {
    const [longitude, latitude] = feature.geometry.coordinates;
    if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) {
      continue;
    }
    west = Math.min(west, longitude);
    south = Math.min(south, latitude);
    east = Math.max(east, longitude);
    north = Math.max(north, latitude);
  }
  return Number.isFinite(west)
    ? [
        [south, west],
        [north, east],
      ]
    : null;
}

export function getFeatureFieldId(feature: Feature): string | undefined {
  const value = feature.properties?.fieldId;
  return isGuid(value) ? value.toLowerCase() : undefined;
}

export function getFeatureParcelId(feature: Feature): number | undefined {
  const value = feature.properties?.parcelId ?? feature.id;
  const id = Number(value);
  return Number.isSafeInteger(id) && id > 0 ? id : undefined;
}
