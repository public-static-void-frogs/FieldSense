import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Button, Typography } from 'antd';
import { CalendarCheck, Check } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { planningMutations } from '../../../api/planning/planning.mutations.ts';
import { RouterButton } from '../../../components/common/RouterButton';
import type { PlannedEvent } from '../../../types/planning/planning.types.ts';
import { useDemoMode } from '../../demo/hooks/useDemoMode.ts';
import { calendarPath } from '../utils/planningRoutes.ts';

type StrategyAcceptanceProps = {
  fieldId: string;
  calendarDate: string;
  events: PlannedEvent[];
  accepted: boolean;
};

export function StrategyAcceptance({
  fieldId,
  calendarDate,
  events,
  accepted,
}: StrategyAcceptanceProps) {
  const { t } = useTranslation();
  const demo = useDemoMode();
  const client = useQueryClient();
  const update = useMutation(planningMutations.respondToStrategy(client));

  if (!events.length) {
    return null;
  }

  return (
    <footer className="strategy-acceptance">
      {accepted && (
        <>
          <div className="strategy-acceptance-status" role="status">
            <Typography.Text strong className="strategy-accepted">
              <Check size={18} aria-hidden="true" />
              {t('Strategy accepted. Events added to your calendar.')}
            </Typography.Text>
            {demo && (
              <Typography.Text className="strategy-acceptance-note" type="secondary">
                {t('This strategy was accepted as part of the demo.')}
              </Typography.Text>
            )}
          </div>
          <RouterButton to={calendarPath(calendarDate, fieldId)}>
            {t('Open field calendar')}
          </RouterButton>
        </>
      )}
      {!accepted && (
        <div className="strategy-acceptance-action">
          <Button
            type="primary"
            size="large"
            icon={<CalendarCheck size={19} />}
            disabled={demo}
            aria-describedby={demo ? 'strategy-demo-calendar-note' : undefined}
            loading={update.isPending}
            onClick={() =>
              update.mutate({ fieldId, status: 'accepted', eventIds: events.map(({ id }) => id) })
            }
          >
            {t('Accept strategy and add to calendar')}
          </Button>
          {demo && (
            <Typography.Text
              id="strategy-demo-calendar-note"
              className="strategy-acceptance-note"
              type="secondary"
            >
              {t('Calendar events are read-only in demo mode.')}
            </Typography.Text>
          )}
        </div>
      )}
      {update.isError && (
        <Typography.Text type="danger" role="alert">
          {t('Unable to save changes')}
        </Typography.Text>
      )}
    </footer>
  );
}
