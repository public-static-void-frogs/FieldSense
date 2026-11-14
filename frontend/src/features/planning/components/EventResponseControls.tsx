import { Button, Space, Tag } from 'antd';
import { Check, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useStrategyResponse } from '../hooks/useStrategyResponse.ts';
import { decisionPresentation } from '../utils/eventPresentation.ts';

type EventResponseControlsProps = { fieldId: string };

export function EventResponseControls({ fieldId }: EventResponseControlsProps) {
  const { t } = useTranslation();
  const { field, events, decision, isRespondingToStrategy, respond } = useStrategyResponse(fieldId);
  if (!field || !events.length) {
    return null;
  }
  const presentation = decisionPresentation[decision];

  return (
    <Space size={8} wrap className="event-response-controls">
      <Tag color={presentation.color}>{t(presentation.label, { value0: events.length })}</Tag>
      <Space.Compact>
        <Button
          size="small"
          type={decision === 'accepted' ? 'primary' : 'default'}
          icon={<Check size={15} />}
          aria-label={t('Accept all strategy events for {{value0}}', { value0: field.name })}
          aria-pressed={decision === 'accepted'}
          disabled={isRespondingToStrategy}
          onClick={(click) => {
            click.stopPropagation();
            void respond('accepted');
          }}
        >
          {t('Accept all')}
        </Button>
        <Button
          size="small"
          danger={decision === 'declined'}
          type={decision === 'declined' ? 'primary' : 'default'}
          icon={<X size={15} />}
          aria-label={t('Reject all strategy events for {{value0}}', { value0: field.name })}
          aria-pressed={decision === 'declined'}
          disabled={isRespondingToStrategy}
          onClick={(click) => {
            click.stopPropagation();
            void respond('declined');
          }}
        >
          {t('Reject all')}
        </Button>
      </Space.Compact>
    </Space>
  );
}
