import { queryOptions } from '@tanstack/react-query';
import { planningApi } from './planning.api.ts';

export const planningQueryKeys = {
  context: () => ['planning', 'context'] as const,
  all: () => ['planning'] as const,
  events: () => ['planning', 'events'] as const,
  fieldEvents: (id: string) => ['planning', 'fields', id, 'events'] as const,
  rotation: (id: string) => ['planning', 'fields', id, 'rotation'] as const,
  strategy: (id: string) => ['planning', 'fields', id, 'strategy'] as const,
  responses: () => ['planning', 'responses'] as const,
};
export const planningQueries = {
  context: () =>
    queryOptions({
      queryKey: planningQueryKeys.context(),
      queryFn: ({ signal }) => planningApi.getContext(signal),
    }),
  events: () =>
    queryOptions({
      queryKey: planningQueryKeys.events(),
      queryFn: ({ signal }) => planningApi.getEvents(signal),
    }),
  fieldEvents: (id: string) =>
    queryOptions({
      queryKey: planningQueryKeys.fieldEvents(id),
      queryFn: ({ signal }) => planningApi.getFieldEvents(id, signal),
    }),
  rotation: (id: string) =>
    queryOptions({
      queryKey: planningQueryKeys.rotation(id),
      queryFn: ({ signal }) => planningApi.getRotation(id, signal),
    }),
  strategy: (id: string) =>
    queryOptions({
      queryKey: planningQueryKeys.strategy(id),
      queryFn: ({ signal }) => planningApi.getStrategy(id, signal),
    }),
  responses: () =>
    queryOptions({
      queryKey: planningQueryKeys.responses(),
      queryFn: ({ signal }) => planningApi.getResponses(signal),
    }),
};
