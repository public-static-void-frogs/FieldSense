import { queryOptions } from '@tanstack/react-query';
import type { User } from '../../types/auth/auth.types.ts';
import { authApi } from './auth.api.ts';

export const authQueryKeys = {
  all: () => ['auth'] as const,
  me: () => ['auth', 'me'] as const,
};

export const authQueries = {
  me: () =>
    queryOptions({
      queryKey: authQueryKeys.me(),
      queryFn: async ({ signal, client }) => {
        const user = await authApi.me(signal);
        const previous = client.getQueryData<User>(authQueryKeys.me());
        if (previous && previous.id !== user.id) {
          const accountQueries = {
            predicate: (query: { queryKey: readonly unknown[] }) => query.queryKey[0] !== 'auth',
          };
          await client.cancelQueries(accountQueries);
          client.removeQueries(accountQueries);
        }
        return user;
      },
      retry: false,
      staleTime: 0,
      refetchInterval: 60_000,
    }),
};
