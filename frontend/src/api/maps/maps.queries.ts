import { keepPreviousData, queryOptions } from '@tanstack/react-query';
import { mapsApi, type MapViewportRequest } from './maps.api.ts';

export const mapQueryKeys = {
  all: () => ['maps'] as const,
  summary: () => ['maps', 'summary'] as const,
  geojson: (viewport: MapViewportRequest) => ['maps', 'geojson', viewport] as const,
};
export const mapQueries = {
  summary: () =>
    queryOptions({
      queryKey: mapQueryKeys.summary(),
      queryFn: ({ signal }) => mapsApi.getSummary(signal),
      staleTime: 300_000,
    }),
  geojson: (viewport: MapViewportRequest) =>
    queryOptions({
      queryKey: mapQueryKeys.geojson(viewport),
      queryFn: ({ signal }) => mapsApi.getGeoJson(viewport, signal),
      placeholderData: keepPreviousData,
      staleTime: 60_000,
      gcTime: 120_000,
    }),
};
