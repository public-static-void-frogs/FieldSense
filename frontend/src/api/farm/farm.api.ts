import type { FarmProfile } from '../../types/farm/farm.types.ts';
import { request } from '../core/http.ts';

export const farmApi = {
  getProfile: (signal?: AbortSignal): Promise<FarmProfile> => request('/farm/profile', { signal }),
};
