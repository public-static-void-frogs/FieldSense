import { queryOptions } from '@tanstack/react-query';
import { notificationsApi } from './notifications.api.ts';

export const notificationQueryKeys = {
  all: () => ['notifications'] as const,
  list: () => ['notifications', 'list'] as const,
};
export const notificationQueries = {
  list: () =>
    queryOptions({
      queryKey: notificationQueryKeys.list(),
      queryFn: ({ signal }) => notificationsApi.getAll(signal),
    }),
};
