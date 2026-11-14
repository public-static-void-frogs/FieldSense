import { useState } from 'react';
import type { PlannedEvent } from '../../../types/planning/planning.types.ts';

type CalendarDrawerActions = {
  changeDate: (date: string) => void;
  openEvent: (event: PlannedEvent) => void;
  clearEvent: () => void;
};

export function useCalendarDrawer(eventId: string | undefined, actions: CalendarDrawerActions) {
  const [dayOpen, setDayOpen] = useState(false);
  function selectDate(date: string) {
    actions.changeDate(date);
    setDayOpen(true);
  }
  function openEvent(event: PlannedEvent) {
    setDayOpen(false);
    actions.openEvent(event);
  }
  function close() {
    setDayOpen(false);
    actions.clearEvent();
  }
  function reset() {
    setDayOpen(false);
  }
  return { isOpen: Boolean(eventId) || dayOpen, selectDate, openEvent, close, reset };
}
