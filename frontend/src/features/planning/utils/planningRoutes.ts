import type { PlannedEvent } from '../../../types/planning/planning.types.ts';

export function calendarPath(date: string, fieldId?: string, eventId?: string): string {
  const params = new URLSearchParams();
  if (fieldId) {
    params.set('field', String(fieldId));
  }
  if (eventId) {
    params.set('event', eventId);
  }
  const query = params.toString();
  return `/calendar/${date}${query ? `?${query}` : ''}`;
}
export function calendarEventPath(event: PlannedEvent): string {
  return calendarPath(event.date, event.fieldId, event.id);
}

export function actionDetailsPath(event: PlannedEvent): string {
  return `/calendar/actions/${encodeURIComponent(event.id)}`;
}
