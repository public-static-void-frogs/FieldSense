import { queryOptions } from '@tanstack/react-query';
import type { TrendParams } from './overview.api.ts';
import { overviewApi } from './overview.api.ts';

export const overviewQueryKeys = {
  all: () => ['overview'] as const,
  charts: (params: TrendParams) =>
    ['overview', 'charts', { days: params.days, metric: params.metric }] as const,
};
export const overviewQueries = {
  charts: (params: TrendParams) =>
    queryOptions({
      queryKey: overviewQueryKeys.charts(params),
      queryFn: ({ signal }) => overviewApi.getCharts(params, signal),
    }),
};
