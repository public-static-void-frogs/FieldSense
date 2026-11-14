import type { UserSettings } from '../../types/auth/auth.types.ts';
import { request } from '../core/http.ts';

export const settingsApi = {
  get: (signal?: AbortSignal): Promise<UserSettings> => request('/users/me/settings', { signal }),
  update: (values: UserSettings): Promise<UserSettings> =>
    request('/users/me/settings', { method: 'PUT', body: JSON.stringify(values) }),
};
