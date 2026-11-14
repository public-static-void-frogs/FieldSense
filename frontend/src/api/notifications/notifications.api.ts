import type { FarmNotification } from '../../types/notifications/notification.types.ts';
import { request } from '../core/http.ts';

export const notificationsApi = {
  getAll: (signal?: AbortSignal): Promise<FarmNotification[]> =>
    request('/notifications', { signal }),
};
