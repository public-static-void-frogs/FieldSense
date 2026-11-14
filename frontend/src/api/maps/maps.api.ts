import type { CatalogMapView, MapBounds, MapSummary } from '../../types/maps/map.types.ts';
import { request } from '../core/http.ts';

export type MapViewportRequest = { bounds: MapBounds; zoom: number };

export const mapsApi = {
  getSummary: (signal?: AbortSignal): Promise<MapSummary> => request('/maps/summary', { signal }),
  getGeoJson: (
    { bounds, zoom }: MapViewportRequest,
    signal?: AbortSignal,
  ): Promise<CatalogMapView> => {
    const query = new URLSearchParams({ bbox: bounds.join(','), zoom: String(zoom) });
    return request(`/maps/geojson?${query}`, { signal });
  },
};
