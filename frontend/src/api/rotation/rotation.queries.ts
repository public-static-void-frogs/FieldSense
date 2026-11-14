import { keepPreviousData, queryOptions } from '@tanstack/react-query';
import type { RotationAdviceRequest } from '../../types/rotation/rotation.types.ts';
import { fieldQueryKeys } from '../fields/fields.queries.ts';
import { rotationApi } from './rotation.api.ts';

export const rotationQueryKeys = {
  advice: ({ fieldId, crop, priorities }: RotationAdviceRequest) =>
    [
      ...fieldQueryKeys.byId(fieldId),
      'rotation-advice',
      crop ?? null,
      [...priorities].sort(),
    ] as const,
};

export const rotationQueries = {
  advice: (input: RotationAdviceRequest) =>
    queryOptions({
      queryKey: rotationQueryKeys.advice(input),
      queryFn: ({ signal }) => rotationApi.getAdvice(input, signal),
      placeholderData: keepPreviousData,
      staleTime: 5 * 60_000,
    }),
};
