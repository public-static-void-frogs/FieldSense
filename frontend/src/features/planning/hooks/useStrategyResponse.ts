import { useMutation, useQueryClient, useSuspenseQuery } from '@tanstack/react-query';
import { App } from 'antd';
import { useTranslation } from 'react-i18next';
import { fieldQueries } from '../../../api/fields/fields.queries.ts';
import { planningMutations } from '../../../api/planning/planning.mutations.ts';
import { planningQueries } from '../../../api/planning/planning.queries.ts';
import type { EventDecision } from '../../../types/planning/planning.types.ts';
import { getStrategyDecision } from '../utils/eventPresentation.ts';

export function useStrategyResponse(fieldId: string) {
  const { t } = useTranslation();
  const { data: events } = useSuspenseQuery(planningQueries.fieldEvents(fieldId));
  const { data: fields } = useSuspenseQuery(fieldQueries.list());
  const { data: eventResponses } = useSuspenseQuery(planningQueries.responses());
  const client = useQueryClient();
  const { mutateAsync: respondToStrategy, isPending: isRespondingToStrategy } = useMutation(
    planningMutations.respondToStrategy(client),
  );
  const { message } = App.useApp();
  const field = fields.find((item) => item.id === fieldId);
  const decision = getStrategyDecision(events, eventResponses);
  function respond(status: EventDecision) {
    return respondToStrategy({ fieldId, status }).catch(() =>
      message.error(t('Unable to save changes')),
    );
  }

  return { field, events, decision, isRespondingToStrategy, respond };
}
