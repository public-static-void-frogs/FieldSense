import { useState } from 'react';

export type CalendarMode = 'month' | 'year';

export function useCalendarView() {
  const [tab, setTab] = useState('calendar');
  const [mode, setMode] = useState<CalendarMode>('month');
  function reset() {
    setMode('month');
  }
  return { tab, setTab, mode, setMode, reset };
}
