import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import type { PlannedEvent } from '../../../types/planning/planning.types.ts';
import { isGuid } from '../../../utils/ids.ts';
import { isPlanDate } from '../utils/planningDates.ts';
import { calendarPath } from '../utils/planningRoutes.ts';

export function useCalendarRoute(today: string) {
  const { date } = useParams<'date'>();
  const [search] = useSearchParams();
  const navigate = useNavigate();
  const rawFieldId = search.get('field');
  const fieldId = isGuid(rawFieldId) ? rawFieldId.toLowerCase() : undefined;
  const eventId = search.get('event') || undefined;
  const selectedDate = isPlanDate(date) ? date! : today;
  function changeDate(value: string) {
    navigate(calendarPath(value, fieldId), { preventScrollReset: true });
  }
  function changeField(value: string) {
    navigate(calendarPath(selectedDate, value === 'all' ? undefined : value), {
      preventScrollReset: true,
    });
  }
  function openEvent(event: PlannedEvent) {
    navigate(calendarPath(event.date, fieldId, event.id), { preventScrollReset: true });
  }
  function clearEvent() {
    changeDate(selectedDate);
  }
  function reset() {
    navigate(calendarPath(today), { preventScrollReset: true });
  }
  return { selectedDate, fieldId, eventId, changeDate, changeField, openEvent, clearEvent, reset };
}
