import { mutationOptions, type QueryClient } from '@tanstack/react-query';
import { planningApi } from './planning.api.ts';
import { planningQueryKeys } from './planning.queries.ts';

export const planningMutations = {
  respondToStrategy: (client: QueryClient) =>
    mutationOptions({
      mutationKey: ['planning', 'respond-to-strategy'],
      mutationFn: planningApi.respondToStrategy,
      onSuccess: async (responses) => {
        await client.cancelQueries({ queryKey: planningQueryKeys.responses() });
        client.setQueryData(planningQueryKeys.responses(), responses);
        await client.invalidateQueries({ queryKey: planningQueryKeys.responses() });
      },
    }),
};
