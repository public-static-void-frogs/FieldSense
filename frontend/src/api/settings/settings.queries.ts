import { queryOptions } from '@tanstack/react-query';
import { settingsApi } from './settings.api.ts';

export const settingsQueryKeys = {
  all: () => ['settings'] as const,
  current: () => ['settings', 'current'] as const,
};

export const settingsQueries = {
  current: () =>
    queryOptions({
      queryKey: settingsQueryKeys.current(),
      queryFn: ({ signal }) => settingsApi.get(signal),
    }),
};
