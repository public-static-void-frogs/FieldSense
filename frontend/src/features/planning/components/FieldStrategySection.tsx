import { useQueries } from '@tanstack/react-query';
import {
  Button,
  Card,
  Descriptions,
  Result,
  Skeleton,
  Space,
  Steps,
  Table,
  Tag,
  Typography,
} from 'antd';
import { CalendarDays, Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { planningQueries } from '../../../api/planning/planning.queries.ts';
import { RouterButton } from '../../../components/common/RouterButton';
import type {
  EventResponses,
  FieldStrategy,
  PlannedEvent,
} from '../../../types/planning/planning.types.ts';
import { countEventDecisions } from '../utils/eventPresentation.ts';
import { formatPlanDate } from '../utils/planningDates.ts';
import { calendarEventPath } from '../utils/planningRoutes.ts';
import { EventDecisionControls } from './EventDecisionControls';
import { StrategyAcceptance } from './StrategyAcceptance';

type FieldStrategySectionProps = { fieldId: string; cropLabel: string };

export function FieldStrategySection({ fieldId, cropLabel }: FieldStrategySectionProps) {
  const { t } = useTranslation();
  const [strategy, responses] = useQueries({
    queries: [planningQueries.strategy(fieldId), planningQueries.responses()],
  });

  if (strategy.data === null || (strategy.data && strategy.data.plan.nextCrop !== cropLabel)) {
    return null;
  }
  if (strategy.isError || responses.isError) {
    return (
      <Result
        status="warning"
        title={t('The rotation strategy could not be loaded')}
        extra={
          <Button onClick={() => void Promise.all([strategy.refetch(), responses.refetch()])}>
            {t('Try again')}
          </Button>
        }
      />
    );
  }
  if (strategy.isPending || responses.isPending) {
    return (
      <Card>
        <Skeleton active paragraph={{ rows: 6 }} />
      </Card>
    );
  }

  return <StrategySections strategy={strategy.data} eventResponses={responses.data} />;
}

type StrategySectionsProps = {
  strategy: FieldStrategy;
  eventResponses: EventResponses;
};

function StrategySections({ strategy, eventResponses }: StrategySectionsProps) {
  const { t } = useTranslation();
  const { plan, events, steps, technicals, contingencies } = strategy;
  const counts = countEventDecisions(events, eventResponses);

  return (
    <section className="strategy-sections" aria-labelledby="field-strategy-heading">
      <header>
        <Typography.Title id="field-strategy-heading" level={2}>
          {t('{{value0}} rotation strategy', { value0: plan.nextCrop })}
        </Typography.Title>
        <Typography.Text type="secondary">
          {t('{{value0}} → {{value1}} → {{value2}} · {{value3}} outlook', {
            value0: plan.currentCrop,
            value1: plan.nextCrop,
            value2: plan.followingCrop,
            value3: `${plan.sowingDate.slice(0, 4)}–${plan.followingDate.slice(0, 4)}`,
          })}
        </Typography.Text>
      </header>

      <Card
        className="ai-insight-card strategy-summary"
        title={
          <Space>
            <Sparkles size={20} className="ai-insight-sparkle" />
            {t('Model recommendation')}
          </Space>
        }
        extra={<Tag className="ai-insight-tag">{t('RULE ENGINE')}</Tag>}
      >
        <Typography.Paragraph>{plan.reasons[0]}</Typography.Paragraph>
        <Descriptions
          column={{ xs: 1, sm: 2, lg: 3 }}
          items={[
            {
              key: 'planting',
              label: t('Planting begins'),
              children: formatPlanDate(plan.sowingDate),
            },
            { key: 'window', label: t('Window ends'), children: formatPlanDate(plan.windowEnd) },
            {
              key: 'confidence',
              label: t('Lead over next-best crop'),
              children: t('{{value0}}%', { value0: plan.confidence }),
            },
          ]}
        />
        <details className="strategy-disclosure">
          <summary>{t('Why this sequence')}</summary>
          {plan.reasons.slice(1).map((reason) => (
            <Typography.Paragraph key={reason}>{reason}</Typography.Paragraph>
          ))}
          <Typography.Title level={5}>{t('How the date was calculated')}</Typography.Title>
          <Typography.Paragraph type="secondary">{plan.dateExplanation}</Typography.Paragraph>
          <Typography.Paragraph type="secondary" className="no-margin">
            {t(
              'Dates are medians of past seasons and the plan comes from the rule engine’s risk scores. It supports your decision; it is not a forecast of yield or weather.',
            )}
          </Typography.Paragraph>
        </details>
        {contingencies.length > 0 && (
          <details className="strategy-disclosure">
            <summary>{t('If conditions change')}</summary>
            {contingencies.map((item) => (
              <div key={item.condition} className="strategy-contingency">
                <Typography.Text strong>{item.condition}</Typography.Text>
                <Typography.Paragraph type="secondary">{item.action}</Typography.Paragraph>
              </div>
            ))}
          </details>
        )}
      </Card>

      <Card title={t('Step-by-step action plan')} className="strategy-action-plan">
        <Steps
          size="small"
          orientation="vertical"
          current={-1}
          items={steps.map(({ event, checkpoint }) => ({
            key: event.id,
            title: <Typography.Text strong>{event.title}</Typography.Text>,
            content: (
              <div className="strategy-step-content">
                <Typography.Text type="secondary">
                  {formatPlanDate(event.date)} · {event.duration}
                </Typography.Text>
                <details className="strategy-disclosure">
                  <summary>{t('Details')}</summary>
                  <Typography.Paragraph>{event.description}</Typography.Paragraph>
                  <Typography.Paragraph type="secondary">
                    <strong>{t('Before moving on:')}</strong> {checkpoint}
                  </Typography.Paragraph>
                  <RouterButton
                    type="link"
                    size="small"
                    to={calendarEventPath(event)}
                    icon={<CalendarDays size={14} />}
                  >
                    {t('Review calendar event')}
                  </RouterButton>
                </details>
              </div>
            ),
          }))}
        />
      </Card>

      <Card>
        <details className="strategy-disclosure">
          <summary>{t('Technical basis')}</summary>
          <Table
            rowKey="key"
            dataSource={technicals}
            pagination={false}
            scroll={{ x: 760 }}
            columns={[
              { title: t('Parameter'), dataIndex: 'parameter', width: 190 },
              { title: t('Current input'), dataIndex: 'value', width: 260 },
              { title: t('How it affects this strategy'), dataIndex: 'role' },
            ]}
          />
        </details>
      </Card>

      <Card
        id="strategy-calendar-proposals"
        title={t('Events proposed to your calendar')}
        className="strategy-proposals strategy-table-card"
      >
        <details className="strategy-disclosure strategy-schedule-details">
          <summary>
            {t('Review proposed events')} ({events.length})
          </summary>
          <Table<PlannedEvent>
            rowKey="id"
            dataSource={events}
            pagination={false}
            scroll={{ x: 760 }}
            columns={[
              {
                title: t('Date'),
                dataIndex: 'date',
                width: 145,
                render: (date) => formatPlanDate(date),
              },
              {
                title: t('Proposed event'),
                dataIndex: 'title',
                render: (title, event) => (
                  <div>
                    <Typography.Text strong>{title}</Typography.Text>
                    <details className="strategy-disclosure">
                      <summary>{t('Details')}</summary>
                      <Typography.Text type="secondary">
                        {event.duration} · {event.rationale}
                      </Typography.Text>
                    </details>
                  </div>
                ),
              },
              {
                title: t('Status'),
                key: 'response',
                width: 250,
                render: (_, event) => <EventDecisionControls event={event} />,
              },
            ]}
          />
        </details>
        <StrategyAcceptance
          fieldId={plan.fieldId}
          calendarDate={plan.sowingDate}
          events={events}
          accepted={counts.accepted === events.length}
        />
      </Card>
    </section>
  );
}
