import type {
  CropHistory,
  CropHistoryLayer,
  CropHistoryPoint,
} from '../../types/fields/crop-history.types.ts';
import { request } from '../core/http.ts';

export const cropHistoryApi = {
  point(id: string, part: number, point: CropHistoryPoint | null, signal: AbortSignal) {
    const params = new URLSearchParams({ part: String(part) });
    if (point) {
      params.set('lon', String(point[0]));
      params.set('lat', String(point[1]));
    }
    return request<CropHistory>(`/fields/${id}/crop-history?${params}`, { signal });
  },
  layer(id: string, part: number, year: number, signal: AbortSignal) {
    return request<CropHistoryLayer>(`/fields/${id}/crop-history/layer/${year}?part=${part}`, {
      signal,
    });
  },
};
