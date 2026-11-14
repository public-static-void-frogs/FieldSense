import type { LocationPoint } from '../../../types/maps/map.types.ts';

export function locationPoint(latitude: number, longitude: number): LocationPoint {
  return {
    latitude: Math.max(-90, Math.min(90, latitude)),
    longitude: ((((longitude + 180) % 360) + 360) % 360) - 180,
  };
}

export function formatLocation(point: LocationPoint): string {
  return `${point.latitude.toFixed(5)}, ${point.longitude.toFixed(5)}`;
}
