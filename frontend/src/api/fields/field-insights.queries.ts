import { queryOptions } from '@tanstack/react-query';
import { fieldInsightsApi } from './field-insights.api.ts';
import { fieldQueryKeys } from './fields.queries.ts';

const tenMinutes = 10 * 60 * 1000;

export const fieldInsightsQueries = {
  soil: (id: string, part: number, geometryKey: string) =>
    queryOptions({
      queryKey: [...fieldQueryKeys.byId(id), 'soil-depletion', part, geometryKey],
      queryFn: ({ signal }) => fieldInsightsApi.soil(id, part, signal),
      refetchInterval: ({ state }) => {
        if (state.status === 'error') {
          return false;
        }
        if (state.data?.status === 'pending') {
          return 1500;
        }
        return state.data?.status === 'busy' ? 8000 : false;
      },
      staleTime: tenMinutes,
      retry: false,
    }),
  m3: (id: string, geometryKey: string) =>
    queryOptions({
      queryKey: [...fieldQueryKeys.byId(id), 'm3-insights', geometryKey],
      queryFn: ({ signal }) => fieldInsightsApi.m3(id, signal),
      staleTime: tenMinutes,
      retry: false,
    }),
};
