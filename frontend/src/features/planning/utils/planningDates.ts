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
export function isPlanDate(date?: string): boolean {
  return (
    !!date &&
    /^\d{4}-\d{2}-\d{2}$/.test(date) &&
    dayjs(date).isValid() &&
    dayjs(date).format('YYYY-MM-DD') === date
  );
}
