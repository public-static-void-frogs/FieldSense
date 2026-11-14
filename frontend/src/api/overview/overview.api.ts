import type { OverviewData, TrendMetric } from '../../types/overview/overview.types.ts';
import { request } from '../core/http.ts';

export type TrendParams = {
  days: number;
  metric: TrendMetric;
};

export const overviewApi = {
  getCharts: (params: TrendParams, signal?: AbortSignal): Promise<OverviewData> =>
    request(
      `/overview/charts?${new URLSearchParams({ days: String(params.days), metric: params.metric })}`,
      { signal },
    ),
};
