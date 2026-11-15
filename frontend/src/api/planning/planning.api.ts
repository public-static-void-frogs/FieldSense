import type {
  EventDecision,
  EventResponses,
  FieldStrategy,
  PlannedEvent,
  PlanningContext,
  RotationPlan,
} from '../../types/planning/planning.types.ts';
import { request } from '../core/http.ts';

type StrategyResponseInput = {
  fieldId: string;
  status: EventDecision;
  eventIds?: string[];
};

type EventResponseInput = StrategyResponseInput & { eventId: string };

// The first call computes the rotation advice, forecast and drought status, which can take a while.
const COMPUTE_TIMEOUT_MS = 45_000;

export const planningApi = {
  getContext: (signal?: AbortSignal): Promise<PlanningContext> =>
    request('/planning/context', { signal }),
  getEvents: (signal?: AbortSignal): Promise<PlannedEvent[]> =>
    request('/planning/events', { signal, timeoutMs: COMPUTE_TIMEOUT_MS }),
  getFieldEvents: async (id: string, signal?: AbortSignal): Promise<PlannedEvent[]> =>
    (await request<PlannedEvent[] | null>(`/fields/${id}/events`, {
      signal,
      allowMissing: true,
      timeoutMs: COMPUTE_TIMEOUT_MS,
    })) ?? [],
  getRotation: (id: string, signal?: AbortSignal): Promise<RotationPlan | null> =>
    request(`/fields/${id}/rotation`, {
      signal,
      allowMissing: true,
      timeoutMs: COMPUTE_TIMEOUT_MS,
    }),
  getStrategy: (id: string, signal?: AbortSignal): Promise<FieldStrategy | null> =>
    request(`/fields/${id}/strategy`, {
      signal,
      allowMissing: true,
      timeoutMs: COMPUTE_TIMEOUT_MS,
    }),
  getResponses: (signal?: AbortSignal): Promise<EventResponses> =>
    request('/planning/responses', { signal }),
  respondToStrategy: ({
    fieldId,
    status,
    eventIds,
  }: StrategyResponseInput): Promise<EventResponses> =>
    request(`/fields/${fieldId}/strategy/response`, {
      method: 'PUT',
      body: JSON.stringify({ status, onlyProposed: !eventIds, eventIds }),
      timeoutMs: COMPUTE_TIMEOUT_MS,
    }),
  respondToEvent: ({ fieldId, eventId, status }: EventResponseInput): Promise<EventResponses> =>
    request(`/fields/${fieldId}/events/${eventId}/response`, {
      method: 'PUT',
      body: JSON.stringify({ status }),
    }),
};
