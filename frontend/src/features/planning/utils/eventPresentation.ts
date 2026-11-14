import type {
  EventDecision,
  EventResponses,
  PlanPriority,
  PlannedEvent,
} from '../../../types/planning/planning.types.ts';
import { getEventDecision } from './eventResponses.ts';
import { getEventStatus } from './planningDates.ts';

export const priorityColors: Record<PlanPriority, string> = {
  'High priority': 'error',
  Important: 'warning',
  Routine: 'default',
};
export const decisionPresentation = {
  accepted: { color: 'success', label: 'All accepted' },
  declined: { color: 'default', label: 'All rejected' },
  proposed: { color: 'processing', label: '{{value0}} proposed events' },
};
export function getStrategyDecision(
  events: PlannedEvent[],
  responses: EventResponses,
): EventDecision {
  if (!events.length) {
    return 'proposed';
  }
  if (events.every((event) => getEventDecision(event, responses) === 'accepted')) {
    return 'accepted';
  }
  if (events.every((event) => getEventDecision(event, responses) === 'declined')) {
    return 'declined';
  }
  return 'proposed';
}
export function countEventDecisions(events: PlannedEvent[], responses: EventResponses) {
  return events.reduce(
    (counts, event) => {
      counts[getEventDecision(event, responses)]++;
      return counts;
    },
    { proposed: 0, accepted: 0, declined: 0 },
  );
}
export function getEventUrgencyColor(event: PlannedEvent, today: string) {
  if (event.priority === 'High priority') {
    return 'error';
  }
  if (getEventStatus(event.date, today) === 'Due soon') {
    return 'warning';
  }
  return 'default';
}
export function filterCalendarEvents(
  events: PlannedEvent[],
  fieldId: string | undefined,
  category: string,
  query: string,
) {
  return events.filter(
    (event) =>
      (!fieldId || event.fieldId === fieldId) &&
      (category === 'All actions' || event.category === category) &&
      `${event.title} ${event.fieldName} ${event.description}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
}
