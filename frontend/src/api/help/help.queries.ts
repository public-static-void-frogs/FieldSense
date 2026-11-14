import { queryOptions } from '@tanstack/react-query';
import { helpApi } from './help.api.ts';

export const helpQueryKeys = {
  all: () => ['help'] as const,
  team: () => ['help', 'team'] as const,
  sources: () => ['help', 'sources'] as const,
};
export const helpQueries = {
  team: () =>
    queryOptions({
      queryKey: helpQueryKeys.team(),
      queryFn: ({ signal }) => helpApi.getTeam(signal),
    }),
  sources: () =>
    queryOptions({
      queryKey: helpQueryKeys.sources(),
      queryFn: ({ signal }) => helpApi.getSources(signal),
    }),
};
