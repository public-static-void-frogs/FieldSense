import { Button, Space, Tag } from 'antd';
import { Check, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useStrategyResponse } from '../hooks/useStrategyResponse.ts';
import { decisionPresentation } from '../utils/eventPresentation.ts';

type EventResponseControlsProps = { fieldId: string };

/**
 * Accept or reject all events of a field at once. Events that were already decided keep their
 * decision, and once none is left to decide only the summary is shown.
 */
export function EventResponseControls({ fieldId }: EventResponseControlsProps) {
  const { t } = useTranslation();
  const { field, events, decision, counts, isRespondingToStrategy, respond } =
    useStrategyResponse(fieldId);
  if (!field || !events.length) {
    return null;
  }
  const presentation = counts.proposed
    ? decisionPresentation.proposed
    : decisionPresentation[decision === 'proposed' ? 'reviewed' : decision];
  const remaining = counts.proposed < events.length;

  return (
    <Space size={8} wrap className="event-response-controls">
      <Tag color={presentation.color}>{t(presentation.label, { value0: counts.proposed })}</Tag>
      {counts.proposed > 0 && (
        <Space.Compact>
          <Button
            size="small"
            icon={<Check size={15} />}
            aria-label={t('Accept all strategy events for {{value0}}', { value0: field.name })}
            disabled={isRespondingToStrategy}
            onClick={(click) => {
              click.stopPropagation();
              void respond('accepted');
            }}
          >
            {remaining ? t('Accept remaining') : t('Accept all')}
          </Button>
          <Button
            size="small"
            icon={<X size={15} />}
            aria-label={t('Reject all strategy events for {{value0}}', { value0: field.name })}
            disabled={isRespondingToStrategy}
            onClick={(click) => {
              click.stopPropagation();
              void respond('declined');
            }}
          >
            {remaining ? t('Reject remaining') : t('Reject all')}
          </Button>
        </Space.Compact>
      )}
    </Space>
  );
}
