import { mutationOptions, type QueryClient } from '@tanstack/react-query';
import type { User } from '../../types/auth/auth.types.ts';
import { farmQueryKeys } from '../farm/farm.queries.ts';
import { authApi } from './auth.api.ts';
import { authQueryKeys } from './auth.queries.ts';

async function startSession(client: QueryClient, user: User) {
  await client.cancelQueries();
  client.clear();
  client.setQueryData(authQueryKeys.me(), user);
}

export const authMutations = {
  login: (client: QueryClient) =>
    mutationOptions({
      mutationFn: authApi.login,
      onSuccess: (user) => startSession(client, user),
    }),
  register: (client: QueryClient) =>
    mutationOptions({
      mutationFn: authApi.register,
      onSuccess: (user) => startSession(client, user),
    }),
  logout: (client: QueryClient) =>
    mutationOptions({
      mutationFn: authApi.logout,
      onSuccess: async () => {
        await client.cancelQueries();
        client.clear();
      },
    }),
  updateAccount: (client: QueryClient) =>
    mutationOptions({
      mutationFn: authApi.updateAccount,
      onSuccess: async (user) => {
        client.setQueryData(authQueryKeys.me(), user);
        await client.invalidateQueries({ queryKey: farmQueryKeys.profile() });
      },
    }),
};
