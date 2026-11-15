import { mutationOptions, type QueryClient } from '@tanstack/react-query';
import { planningApi } from './planning.api.ts';
import { planningQueryKeys } from './planning.queries.ts';

async function saveResponses(
  client: QueryClient,
  responses: Awaited<ReturnType<typeof planningApi.getResponses>>,
) {
  await client.cancelQueries({ queryKey: planningQueryKeys.responses() });
  client.setQueryData(planningQueryKeys.responses(), responses);
  await client.invalidateQueries({ queryKey: planningQueryKeys.responses() });
}

export const planningMutations = {
  respondToStrategy: (client: QueryClient) =>
    mutationOptions({
      mutationKey: ['planning', 'respond-to-strategy'],
      mutationFn: planningApi.respondToStrategy,
      onSuccess: (responses) => saveResponses(client, responses),
    }),
  respondToEvent: (client: QueryClient) =>
    mutationOptions({
      mutationKey: ['planning', 'respond-to-event'],
      mutationFn: planningApi.respondToEvent,
      onSuccess: (responses) => saveResponses(client, responses),
    }),
};
