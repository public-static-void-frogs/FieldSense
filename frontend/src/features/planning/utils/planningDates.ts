import dayjs from 'dayjs';
import type { EventStatus } from '../../../types/planning/planning.types.ts';

export function formatPlanDate(date: string): string {
  return dayjs(date).format(dayjs.locale() === 'uk' ? 'D MMMM YYYY' : 'MMMM D, YYYY');
}
export function getEventStatus(date: string, planningToday: string): EventStatus {
  if (date < planningToday) {
    return 'Completed';
  }
  return date <= dayjs(planningToday).add(7, 'day').format('YYYY-MM-DD') ? 'Due soon' : 'Planned';
}
/**
 * The day the calendar opens on. Today when the current month has actions; otherwise the next
 * upcoming action, so a farmer whose plan starts in a later month does not see an empty grid.
 */
export function defaultCalendarDate(dates: string[], planningToday: string): string {
  const month = planningToday.slice(0, 7);
  if (dates.some((date) => date.startsWith(month))) {
    return planningToday;
  }
  const upcoming = dates.filter((date) => date > planningToday).sort();

  return upcoming[0] ?? planningToday;
}
export function isPlanDate(date?: string): boolean {
  return (
    !!date &&
    /^\d{4}-\d{2}-\d{2}$/.test(date) &&
    dayjs(date).isValid() &&
    dayjs(date).format('YYYY-MM-DD') === date
  );
}
