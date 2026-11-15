import { useSuspenseQuery } from '@tanstack/react-query';
import { Button, Space, Tag } from 'antd';
import { Check, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { planningQueries } from '../../../api/planning/planning.queries.ts';
import type { PlannedEvent } from '../../../types/planning/planning.types.ts';
import { useEventResponse } from '../hooks/useEventResponse.ts';
import { getEventDecision } from '../utils/eventResponses.ts';

type EventDecisionControlsProps = { event: PlannedEvent };

const decidedTags = {
  accepted: { color: 'success', label: 'Accepted' },
  declined: { color: 'default', label: 'Rejected' },
} as const;

/**
 * The state of one event. While it is only proposed it has Accept and Reject buttons; once it is
 * decided only its state is shown, so there is nothing left to click.
 */
export function EventDecisionControls({ event }: EventDecisionControlsProps) {
  const { t } = useTranslation();
  const { data: responses } = useSuspenseQuery(planningQueries.responses());
  const { respond, isPending } = useEventResponse(event);
  const decision = getEventDecision(event, responses);
  if (decision !== 'proposed') {
    const tag = decidedTags[decision];

    return (
      <Tag color={tag.color} className="event-decision-tag">
        {t(tag.label)}
      </Tag>
    );
  }

  return (
    <Space size={6} wrap className="event-decision-controls">
      <Tag color="processing" className="event-decision-tag">
        {t('Proposed')}
      </Tag>
      <Button
        size="small"
        type="primary"
        icon={<Check size={15} />}
        aria-label={t('Accept event: {{value0}}', { value0: event.title })}
        disabled={isPending}
        onClick={(click) => {
          click.stopPropagation();
          void respond('accepted');
        }}
      >
        {t('Accept')}
      </Button>
      <Button
        size="small"
        icon={<X size={15} />}
        aria-label={t('Reject event: {{value0}}', { value0: event.title })}
        disabled={isPending}
        onClick={(click) => {
          click.stopPropagation();
          void respond('declined');
        }}
      >
        {t('Reject')}
      </Button>
    </Space>
  );
}
