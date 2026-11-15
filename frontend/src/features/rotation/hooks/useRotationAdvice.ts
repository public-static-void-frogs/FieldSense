import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { rotationQueries } from '../../../api/rotation/rotation.queries.ts';
import type { RotationPlanner, RotationPriority } from '../../../types/rotation/rotation.types.ts';
import { priorityOptions } from '../constants/rotationLabels.ts';
import { parseSeasons } from '../utils/planPresentation.ts';

export function useRotationAdvice(fieldId: string) {
  const [search, setSearch] = useSearchParams();
  const crop = search.get('crop') || undefined;
  const priorities = priorityOptions
    .map(({ value }) => value)
    .filter((value) => search.getAll('priorities').includes(value));
  const seasons = parseSeasons(search.get('seasons'));
  const planner: RotationPlanner = search.get('planner') === 'learned' ? 'learned' : 'exact';
  const query = useQuery(rotationQueries.advice({ fieldId, crop, priorities, seasons, planner }));

  const setCrop = (selected: string) => {
    const next = new URLSearchParams(search);
    next.set('crop', selected);
    setSearch(next, { replace: true, preventScrollReset: true });
  };

  const setSeasons = (selected: number) => {
    const next = new URLSearchParams(search);
    next.set('seasons', String(selected));
    setSearch(next, { replace: true, preventScrollReset: true });
  };

  const setPlanner = (selected: RotationPlanner) => {
    const next = new URLSearchParams(search);
    if (selected === 'learned') {
      next.set('planner', selected);
    } else {
      next.delete('planner');
    }
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
    selectedSeasons: seasons,
    selectedPlanner: planner,
    priorities,
    setCrop,
    setSeasons,
    setPlanner,
    togglePriority,
  };
}
