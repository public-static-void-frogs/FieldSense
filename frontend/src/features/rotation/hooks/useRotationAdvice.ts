import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { rotationQueries } from '../../../api/rotation/rotation.queries.ts';
import type { RotationPriority } from '../../../types/rotation/rotation.types.ts';

export function useRotationAdvice(fieldId: string) {
  const [crop, setCrop] = useState<string>();
  const [priorities, setPriorities] = useState<RotationPriority[]>([]);
  const query = useQuery(rotationQueries.advice({ fieldId, crop, priorities }));

  const togglePriority = (priority: RotationPriority, selected: boolean) => {
    setPriorities((current) =>
      selected ? [...current, priority] : current.filter((item) => item !== priority),
    );
  };

  return {
    advice: query.data,
    isLoading: query.isPending,
    isUpdating: query.isFetching && query.isPlaceholderData,
    error: query.error,
    retry: query.refetch,
    priorities,
    setCrop,
    togglePriority,
  };
}
