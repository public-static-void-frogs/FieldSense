import type {
  CurrentSoilMoisture,
  MoisturePeriod,
  SoilMoistureComparison,
  SoilMoistureHistory,
} from '../../types/fields/soil-moisture.types.ts';
import { request } from '../core/http.ts';

export const soilMoistureApi = {
  current: (id: string, part: number, signal: AbortSignal) =>
    request<CurrentSoilMoisture>(`/fields/${id}/soil-moisture?part=${part}`, { signal }),
  history: (id: string, part: number, period: MoisturePeriod, signal: AbortSignal) => {
    const params = new URLSearchParams({ ...period, part: String(part) });

    return request<SoilMoistureHistory>(`/fields/${id}/soil-moisture/history?${params}`, {
      signal,
    });
  },
  comparison: (id: string, part: number, signal: AbortSignal) =>
    request<SoilMoistureComparison>(`/fields/${id}/soil-moisture/comparison?part=${part}`, {
      signal,
    }),
};
