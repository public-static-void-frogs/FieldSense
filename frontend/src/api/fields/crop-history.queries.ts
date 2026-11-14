import { keepPreviousData, queryOptions, skipToken } from '@tanstack/react-query';
import type { CropHistoryPoint } from '../../types/fields/crop-history.types.ts';
import { cropHistoryApi } from './crop-history.api.ts';

const staleTime = 60 * 60 * 1000;

export const cropHistoryQueries = {
  point(id: string, part: number, geometryKey: string, point: CropHistoryPoint | null) {
    return queryOptions({
      queryKey: ['fields', id, 'crop-history', geometryKey, part, 'point', point],
      queryFn: ({ signal }) => cropHistoryApi.point(id, part, point, signal),
      staleTime,
      placeholderData: keepPreviousData,
      retry: false,
    });
  },
  layer(id: string, part: number, geometryKey: string, year: number | undefined) {
    return queryOptions({
      queryKey: ['fields', id, 'crop-history', geometryKey, part, 'layer', year],
      queryFn:
        year === undefined
          ? skipToken
          : ({ signal }) => cropHistoryApi.layer(id, part, year, signal),
      staleTime,
      placeholderData: keepPreviousData,
      retry: false,
    });
  },
};
