import type { MapViewportRequest } from '../../../api/maps/maps.api.ts';

export function normalizeViewport(
  west: number,
  south: number,
  east: number,
  north: number,
  zoom: number,
): MapViewportRequest {
  const round = (value: number) => Math.round(value * 100_000) / 100_000;
  return {
    bounds: [
      Math.max(-180, round(west)),
      Math.max(-90, round(south)),
      Math.min(180, round(east)),
      Math.min(90, round(north)),
    ],
    zoom: Math.max(0, Math.min(20, Math.floor(zoom))),
  };
}

export function parseMapPosition(parameters: URLSearchParams) {
  if (!['lat', 'lon', 'zoom'].every((key) => parameters.get(key)?.trim())) {
    return null;
  }
  const latitude = Number(parameters.get('lat'));
  const longitude = Number(parameters.get('lon'));
  const zoom = Number(parameters.get('zoom'));
  if (
    ![latitude, longitude, zoom].every(Number.isFinite) ||
    latitude < -85 ||
    latitude > 85 ||
    longitude < -180 ||
    longitude > 180 ||
    zoom < 2 ||
    zoom > 19
  ) {
    return null;
  }
  return { center: [latitude, longitude] as [number, number], zoom };
}

export function clusterView(
  bounds: import('../../../types/maps/map.types.ts').MapBounds,
  zoom: number,
) {
  return {
    center: [(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2] as [number, number],
    zoom: Math.min(19, zoom + 2),
  };
}
