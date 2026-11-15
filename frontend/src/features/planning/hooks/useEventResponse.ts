import { useMutation, useQueryClient } from '@tanstack/react-query';
import { App } from 'antd';
import { useTranslation } from 'react-i18next';
import { planningMutations } from '../../../api/planning/planning.mutations.ts';
import type { EventDecision, PlannedEvent } from '../../../types/planning/planning.types.ts';

/** Accept or reject one calendar event. */
export function useEventResponse(event: PlannedEvent) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const { message } = App.useApp();
  const { mutateAsync, isPending } = useMutation(planningMutations.respondToEvent(client));

  function respond(status: EventDecision) {
    return mutateAsync({ fieldId: event.fieldId, eventId: event.id, status }).catch(() =>
      message.error(t('Unable to save changes')),
    );
  }

  return { respond, isPending };
}
