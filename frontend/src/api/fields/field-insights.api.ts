import type {
  M2Insights,
  M3Insights,
  SoilDepletion,
} from '../../types/fields/field-insights.types.ts';
import { request } from '../core/http.ts';

export const fieldInsightsApi = {
  soil: (id: string, part: number, signal: AbortSignal) =>
    request<SoilDepletion>(`/fields/${id}/soil-depletion?part=${part}`, { signal }),
  m2: (id: string, signal: AbortSignal) =>
    request<M2Insights>(`/fields/${id}/m2-insights`, { signal }),
  m3: (id: string, signal: AbortSignal) =>
    request<M3Insights>(`/fields/${id}/m3-insights`, { signal }),
};
