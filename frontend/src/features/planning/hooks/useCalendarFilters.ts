import { useState } from 'react';
import type { PlannedEvent } from '../../../types/planning/planning.types.ts';

import { filterCalendarEvents } from '../utils/eventPresentation.ts';

const initialFilters: CalendarFilters = { category: 'All actions', query: '' };
type CalendarFilters = {
  category: string;
  query: string;
};

export function useCalendarFilters(events: PlannedEvent[], fieldId?: string) {
  const [criteria, setCriteria] = useState(initialFilters);
  function update(patch: Partial<CalendarFilters>) {
    setCriteria((current) => ({ ...current, ...patch }));
  }
  function reset() {
    setCriteria(initialFilters);
  }
  const visible = filterCalendarEvents(events, fieldId, criteria.category, criteria.query);
  return { criteria, update, reset, visible };
}
