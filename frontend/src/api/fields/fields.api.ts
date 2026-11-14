import type {
  CropOption,
  FieldHistory,
  FieldPropertyData,
  FieldRecommendationData,
} from '../../types/fields/api.types.ts';
import type { Field } from '../../types/fields/field.types.ts';
import type { CropZone } from '../../types/maps/map.types.ts';
import { request } from '../core/http.ts';

export type CreateFieldInput = {
  parcelId?: number;
  area: number;
  geometry: Field['geometry'];
  crop: string;
};

export const fieldsApi = {
  getAll: (signal?: AbortSignal): Promise<Field[]> => request('/fields', { signal }),
  getCatalogById: (id: string, signal?: AbortSignal): Promise<Field | null> =>
    request(`/fields/catalog/${id}`, { signal, allowMissing: true }),
  select: (id: string): Promise<Field> => request(`/fields/${id}/selection`, { method: 'PUT' }),
  getById: (id: string, signal?: AbortSignal): Promise<Field | null> =>
    request(`/fields/${id}`, { signal, allowMissing: true }),
  getCrops: (signal?: AbortSignal): Promise<CropOption[]> => request('/crops', { signal }),
  getProperties: (id: string, signal?: AbortSignal): Promise<FieldPropertyData | null> =>
    request(`/fields/${id}/properties`, { signal, allowMissing: true }),
  getHistory: (id: string, signal?: AbortSignal): Promise<FieldHistory | null> =>
    request(`/fields/${id}/history`, { signal, allowMissing: true }),
  getRecommendation: (id: string, signal?: AbortSignal): Promise<FieldRecommendationData | null> =>
    request(`/fields/${id}/recommendation`, { signal, allowMissing: true }),
  create: (input: CreateFieldInput): Promise<Field> =>
    request('/fields', { method: 'POST', body: JSON.stringify(input) }),
  saveCropAreas: (areas: Pick<CropZone, 'crop' | 'geometry'>[]): Promise<Field[]> =>
    request('/fields/crop-areas', { method: 'POST', body: JSON.stringify({ areas }) }),
  remove: (id: string): Promise<string> => request(`/fields/${id}`, { method: 'DELETE' }),
};
