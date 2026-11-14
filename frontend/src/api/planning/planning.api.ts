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
};

export const planningApi = {
  getContext: (signal?: AbortSignal): Promise<PlanningContext> =>
    request('/planning/context', { signal }),
  getEvents: (signal?: AbortSignal): Promise<PlannedEvent[]> =>
    request('/planning/events', { signal }),
  getFieldEvents: async (id: string, signal?: AbortSignal): Promise<PlannedEvent[]> =>
    (await request<PlannedEvent[] | null>(`/fields/${id}/events`, {
      signal,
      allowMissing: true,
    })) ?? [],
  getRotation: (id: string, signal?: AbortSignal): Promise<RotationPlan | null> =>
    request(`/fields/${id}/rotation`, { signal, allowMissing: true }),
  getStrategy: (id: string, signal?: AbortSignal): Promise<FieldStrategy | null> =>
    request(`/fields/${id}/strategy`, { signal, allowMissing: true }),
  getResponses: (signal?: AbortSignal): Promise<EventResponses> =>
    request('/planning/responses', { signal }),
  respondToStrategy: ({ fieldId, status }: StrategyResponseInput): Promise<EventResponses> =>
    request(`/fields/${fieldId}/strategy/response`, {
      method: 'PUT',
      body: JSON.stringify({ status }),
    }),
};
