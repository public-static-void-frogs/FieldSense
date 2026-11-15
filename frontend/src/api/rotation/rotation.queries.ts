import { keepPreviousData, queryOptions } from '@tanstack/react-query';
import type { RotationAdviceRequest } from '../../types/rotation/rotation.types.ts';
import { fieldQueryKeys } from '../fields/fields.queries.ts';
import { rotationApi } from './rotation.api.ts';

export const rotationQueryKeys = {
  /** Everything the advice for a field is built from: the advice and the farmer's inputs. */
  field: (fieldId: string) => [...fieldQueryKeys.byId(fieldId), 'rotation'] as const,
  advice: ({ fieldId, crop, priorities, seasons }: RotationAdviceRequest) =>
    [
      ...rotationQueryKeys.field(fieldId),
      'advice',
      crop ?? null,
      [...priorities].sort(),
      seasons ?? null,
    ] as const,
  seasonResults: (fieldId: string) =>
    [...rotationQueryKeys.field(fieldId), 'season-results'] as const,
  soilSurvey: (fieldId: string) => [...rotationQueryKeys.field(fieldId), 'soil-survey'] as const,
  economics: (fieldId: string) => [...rotationQueryKeys.field(fieldId), 'economics'] as const,
};

export const rotationQueries = {
  advice: (input: RotationAdviceRequest) =>
    queryOptions({
      queryKey: rotationQueryKeys.advice(input),
      queryFn: ({ signal }) => rotationApi.getAdvice(input, signal),
      placeholderData: keepPreviousData,
      staleTime: 5 * 60_000,
    }),
  seasonResults: (fieldId: string) =>
    queryOptions({
      queryKey: rotationQueryKeys.seasonResults(fieldId),
      queryFn: ({ signal }) => rotationApi.getSeasonResults(fieldId, signal),
      staleTime: 5 * 60_000,
    }),
  soilSurvey: (fieldId: string) =>
    queryOptions({
      queryKey: rotationQueryKeys.soilSurvey(fieldId),
      queryFn: ({ signal }) => rotationApi.getSoilSurvey(fieldId, signal),
      staleTime: 5 * 60_000,
    }),
  economics: (fieldId: string) =>
    queryOptions({
      queryKey: rotationQueryKeys.economics(fieldId),
      queryFn: ({ signal }) => rotationApi.getEconomics(fieldId, signal),
      staleTime: 5 * 60_000,
    }),
};
