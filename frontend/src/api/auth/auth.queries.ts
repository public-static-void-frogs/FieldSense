import { queryOptions } from '@tanstack/react-query';
import { authApi } from './auth.api.ts';

export const authQueryKeys = {
  all: () => ['auth'] as const,
  me: () => ['auth', 'me'] as const,
};

export const authQueries = {
  me: () =>
    queryOptions({
      queryKey: authQueryKeys.me(),
      queryFn: ({ signal }) => authApi.me(signal),
      retry: false,
      staleTime: 0,
      refetchInterval: 60_000,
    }),
};
