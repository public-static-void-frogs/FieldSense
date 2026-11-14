import type {
  EventDecision,
  EventResponses,
  PlannedEvent,
} from '../../../types/planning/planning.types.ts';

// Responses apply to the reviewed schedule, not a later replacement with the same ID.
export function eventFingerprint(event: PlannedEvent): string {
  return JSON.stringify([
    event.id,
    event.fieldId,
    event.date,
    event.title,
    event.description,
    event.duration,
  ]);
}

export function getEventDecision(event: PlannedEvent, responses: EventResponses): EventDecision {
  const response = responses[event.id];
  return response?.fingerprint === eventFingerprint(event) ? response.status : 'proposed';
}

export function getCalendarEvents(
  events: PlannedEvent[],
  responses: EventResponses,
): PlannedEvent[] {
  return events.filter((event) => getEventDecision(event, responses) !== 'declined');
}
