import { queryOptions } from '@tanstack/react-query';
import { fieldsApi } from './fields.api.ts';
import { sampleFieldRecommendation } from './mocks/fieldRecommendation.ts';

export const fieldQueryKeys = {
  all: () => ['fields'] as const,
  list: () => [...fieldQueryKeys.all(), 'list'] as const,
  byId: (id: string) => [...fieldQueryKeys.all(), 'detail', id] as const,
  catalogById: (id: string) => [...fieldQueryKeys.all(), 'catalog', id] as const,
  crops: () => [...fieldQueryKeys.all(), 'crops'] as const,
  properties: (id: string) => [...fieldQueryKeys.byId(id), 'properties'] as const,
  history: (id: string) => [...fieldQueryKeys.byId(id), 'history'] as const,
  recommendation: (id: string) => [...fieldQueryKeys.byId(id), 'recommendation'] as const,
};
export const fieldQueries = {
  list: () =>
    queryOptions({
      queryKey: fieldQueryKeys.list(),
      queryFn: ({ signal }) => fieldsApi.getAll(signal),
    }),
  byId: (id: string) =>
    queryOptions({
      queryKey: fieldQueryKeys.byId(id),
      queryFn: ({ signal }) => fieldsApi.getById(id, signal),
    }),
  catalogById: (id: string) =>
    queryOptions({
      queryKey: fieldQueryKeys.catalogById(id),
      queryFn: ({ signal }) => fieldsApi.getCatalogById(id, signal),
    }),
  crops: () =>
    queryOptions({
      queryKey: fieldQueryKeys.crops(),
      queryFn: ({ signal }) => fieldsApi.getCrops(signal),
    }),
  properties: (id: string) =>
    queryOptions({
      queryKey: fieldQueryKeys.properties(id),
      queryFn: ({ signal }) => fieldsApi.getProperties(id, signal),
    }),
  history: (id: string) =>
    queryOptions({
      queryKey: fieldQueryKeys.history(id),
      queryFn: ({ signal }) => fieldsApi.getHistory(id, signal),
    }),
  recommendation: (id: string) =>
    queryOptions({
      queryKey: fieldQueryKeys.recommendation(id),
      queryFn: async ({ signal }) => {
        const recommendation = await fieldsApi.getRecommendation(id, signal);
        return {
          recommendation: recommendation ?? sampleFieldRecommendation,
          isSample: !recommendation,
        };
      },
    }),
};
