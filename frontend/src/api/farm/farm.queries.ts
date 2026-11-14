import { queryOptions } from '@tanstack/react-query';
import { farmApi } from './farm.api.ts';

export const farmQueryKeys = {
  all: () => ['farm'] as const,
  profile: () => ['farm', 'profile'] as const,
};
export const farmQueries = {
  profile: () =>
    queryOptions({
      queryKey: farmQueryKeys.profile(),
      queryFn: ({ signal }) => farmApi.getProfile(signal),
    }),
};
