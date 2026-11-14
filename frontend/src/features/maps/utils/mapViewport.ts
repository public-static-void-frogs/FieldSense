import { geoJSON, latLngBounds, type Map as LeafletMap } from 'leaflet';
import type { Field } from '../../../types/fields/field.types.ts';
import type { FieldGeoJson } from '../../../types/maps/map.types.ts';
import { getGeoJsonBounds } from './mapGeometry.ts';

export const defaultCenter: [number, number] = [42.042, -93.737];
const fitOptions = { padding: [50, 100] as [number, number], maxZoom: 16, animate: false };

export function fitParcels(map: LeafletMap, data: FieldGeoJson, fields: Field[]) {
  const bounds = latLngBounds(getGeoJsonBounds(data) ?? []);
  for (const field of fields) {
    if (field.boundary) {
      bounds.extend(geoJSON(field.boundary).getBounds());
    }
  }
  if (bounds.isValid()) {
    map.fitBounds(bounds, fitOptions);
  } else {
    map.setView(defaultCenter, 14);
  }
}
