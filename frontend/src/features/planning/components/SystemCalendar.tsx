import { useSuspenseQuery } from '@tanstack/react-query';
import { Calendar } from 'antd';
import type { Dayjs } from 'dayjs';
import { planningQueries } from '../../../api/planning/planning.queries.ts';
import type { PlannedEvent } from '../../../types/planning/planning.types.ts';
import type { CalendarMode } from '../hooks/useCalendarView.ts';

import { useSystemCalendar } from '../hooks/useSystemCalendar.ts';
import { CalendarCell } from './CalendarCell.tsx';

type SystemCalendarProps = {
  value: Dayjs;
  events: PlannedEvent[];
  onDateSelect: (date: string) => void;
  onPanelDateChange: (date: string) => void;
  onEventSelect: (event: PlannedEvent) => void;
  mode: CalendarMode;
  onModeChange: (mode: CalendarMode) => void;
};

export function SystemCalendar({
  value,
  events,
  onDateSelect,
  onEventSelect,
  mode,
  onModeChange,
  onPanelDateChange,
}: SystemCalendarProps) {
  const { compact, selectDate, changePanel } = useSystemCalendar({
    onDateSelect,
    onModeChange,
    onPanelDateChange,
  });
  const { data: eventResponses } = useSuspenseQuery(planningQueries.responses());

  return (
    <Calendar
      className={`system-calendar ${compact ? 'system-calendar-compact' : ''}`}
      fullscreen
      value={value}
      mode={mode}
      cellRender={(date, info) => (
        <CalendarCell
          date={date}
          info={info}
          events={events}
          compact={compact}
          eventResponses={eventResponses}
          onDateSelect={onDateSelect}
          onEventSelect={onEventSelect}
        />
      )}
      onSelect={selectDate}
      onPanelChange={changePanel}
    />
  );
}
