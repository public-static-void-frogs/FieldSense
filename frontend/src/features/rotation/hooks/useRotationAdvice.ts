import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { rotationQueries } from '../../../api/rotation/rotation.queries.ts';
import type { RotationPriority } from '../../../types/rotation/rotation.types.ts';
import { priorityOptions } from '../constants/rotationLabels.ts';

export function useRotationAdvice(fieldId: string) {
  const [search, setSearch] = useSearchParams();
  const crop = search.get('crop') || undefined;
  const priorities = priorityOptions
    .map(({ value }) => value)
    .filter((value) => search.getAll('priorities').includes(value));
  const query = useQuery(rotationQueries.advice({ fieldId, crop, priorities }));

  const setCrop = (selected: string) => {
    const next = new URLSearchParams(search);
    next.set('crop', selected);
    setSearch(next, { replace: true, preventScrollReset: true });
  };

  const togglePriority = (priority: RotationPriority, selected: boolean) => {
    const next = new URLSearchParams(search);
    next.delete('priorities', priority);
    if (selected) {
      next.append('priorities', priority);
    }
    setSearch(next, { replace: true, preventScrollReset: true });
  };

  return {
    advice: query.data,
    isLoading: query.isPending,
    isUpdating: query.isFetching && query.isPlaceholderData,
    error: query.error,
    retry: query.refetch,
    selectedCrop: crop,
    priorities,
    setCrop,
    togglePriority,
  };
}
