import { useQueries } from '@tanstack/react-query';
import {
  Button,
  Card,
  Descriptions,
  Flex,
  Result,
  Skeleton,
  Space,
  Steps,
  Table,
  Tag,
  Typography,
} from 'antd';
import dayjs from 'dayjs';
import { ArrowUpRight, CalendarDays, Sparkles } from 'lucide-react';
import { Suspense } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { planningQueries } from '../../../api/planning/planning.queries.ts';
import { RouterButton } from '../../../components/common/RouterButton';
import type { Field } from '../../../types/fields/field.types.ts';
import type {
  EventResponses,
  FieldStrategy,
  PlannedEvent,
} from '../../../types/planning/planning.types.ts';
import { useStrategyReview } from '../hooks/useStrategyReview.ts';
import { countEventDecisions } from '../utils/eventPresentation.ts';
import { formatPlanDate } from '../utils/planningDates.ts';
import { calendarEventPath, calendarPath } from '../utils/planningRoutes.ts';
import { EventResponseControls } from './EventResponseControls';

const tooltipStyle = {
  border: '1px solid #dfe5d5',
  borderRadius: 8,
  background: '#fff',
  fontSize: 13,
};
const axis = { fill: '#707d65', fontSize: 12 };

type FieldStrategySectionProps = { field: Field };

export function FieldStrategySection({ field }: FieldStrategySectionProps) {
  const { t } = useTranslation();
  const [strategy, responses] = useQueries({
    queries: [planningQueries.strategy(field.id), planningQueries.responses()],
  });

  if (strategy.data === null) {
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

  return (
    <StrategySections field={field} strategy={strategy.data} eventResponses={responses.data} />
  );
}

type StrategySectionsProps = {
  field: Field;
  strategy: FieldStrategy;
  eventResponses: EventResponses;
};

function StrategySections({ field, strategy, eventResponses }: StrategySectionsProps) {
  const { t } = useTranslation();
  const { animate, reviewEvents } = useStrategyReview();
  const forecastMetrics = [
    {
      title: t('Rotation fit'),
      currentKey: 'currentHealth',
      projectedKey: 'health',
      gainKey: 'healthImprovement',
      color: '#476b3c',
      unit: '/100',
      deltaUnit: t('points'),
      description: t(
        'Rule-engine fit of the recommended crop against the current crop, rescaled across all candidate crops: 100 is the best-scoring crop, 0 the worst. It compares crops for this field; it does not predict yield.',
      ),
    },
  ] as const;

  const { plan, events, steps, forecast, comparison, technicals, contingencies } = strategy;
  const counts = countEventDecisions(events, eventResponses);

  return (
    <section className="strategy-sections" aria-labelledby="field-strategy-heading">
      <Flex justify="space-between" align="center" gap={20} wrap>
        <div>
          <Typography.Title id="field-strategy-heading" level={2}>
            {t('{{value0}} rotation strategy', { value0: plan.nextCrop })}
          </Typography.Title>
          <Typography.Text type="secondary">
            {t('{{value0}} → {{value1}} → {{value2}} · {{value3}} outlook', {
              value0: field.crop,
              value1: plan.nextCrop,
              value2: plan.followingCrop,
              value3: `${plan.sowingDate.slice(0, 4)}–${plan.followingDate.slice(0, 4)}`,
            })}
          </Typography.Text>
        </div>
        <Space wrap>
          <Button onClick={reviewEvents}>{t('Review proposed events')}</Button>
          <RouterButton
            icon={<CalendarDays size={18} />}
            to={calendarPath(plan.sowingDate, field.id)}
          >
            {t('Open field calendar')}
          </RouterButton>
        </Space>
      </Flex>

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
        <Typography.Paragraph type="secondary" className="strategy-demo-note">
          {t(
            'Dates are medians of past seasons and the plan comes from the rule engine’s risk scores. It supports your decision; it is not a forecast of yield or weather.',
          )}
        </Typography.Paragraph>
      </Card>

      <div className="strategy-content-grid">
        <Card title={t('Step-by-step action plan')}>
          <Steps
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
                </div>
              ),
            }))}
          />
        </Card>
        <div className="strategy-sidebar">
          <Card title={t('Why this sequence')}>
            {plan.reasons.slice(1).map((reason) => (
              <Typography.Paragraph key={reason}>{reason}</Typography.Paragraph>
            ))}
            <Typography.Title level={5}>{t('How the date was calculated')}</Typography.Title>
            <Typography.Paragraph type="secondary" className="no-margin">
              {plan.dateExplanation}
            </Typography.Paragraph>
          </Card>
          <Card title={t('If conditions change')}>
            {contingencies.map((item) => (
              <div key={item.condition} className="strategy-contingency">
                <Typography.Text strong>{item.condition}</Typography.Text>
                <Typography.Paragraph type="secondary">{item.action}</Typography.Paragraph>
              </div>
            ))}
          </Card>
        </div>
      </div>

      <section aria-label={t('Strategy fit comparison')} className="strategy-forecast-grid">
        {forecastMetrics.map((metric, index) => {
          const values = comparison[index];
          const delta = values.projected - values.current;

          return (
            <Card
              key={metric.projectedKey}
              title={metric.title}
              extra={<Tag>{t('Score-based')}</Tag>}
            >
              <div className="strategy-forecast-summary">
                <div>
                  <Typography.Text type="secondary">{t('Current')}</Typography.Text>
                  <Typography.Text strong>
                    {values.current}
                    {metric.unit}
                  </Typography.Text>
                </div>
                <ArrowUpRight size={18} aria-hidden="true" />
                <div>
                  <Typography.Text type="secondary">{t('Projected')}</Typography.Text>
                  <Typography.Text strong>
                    {values.projected}
                    {metric.unit}
                  </Typography.Text>
                </div>
                <Tag color="success">
                  {delta > 0 ? '+' : ''}
                  {delta} {metric.deltaUnit}
                </Tag>
              </div>
              <div className="strategy-chart">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart
                    data={forecast}
                    margin={{ top: 15, right: 16, left: 0, bottom: 6 }}
                    accessibilityLayer
                  >
                    <CartesianGrid vertical={false} stroke="#e5eadc" />
                    <XAxis
                      dataKey="date"
                      tickFormatter={(date) => dayjs(date).format('MMM YY')}
                      minTickGap={30}
                      tick={axis}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      domain={[0, 100]}
                      tick={axis}
                      axisLine={false}
                      tickLine={false}
                      width={36}
                    />
                    <Tooltip
                      contentStyle={tooltipStyle}
                      labelFormatter={(date) => formatPlanDate(String(date))}
                      formatter={(value) => `${value}${metric.unit}`}
                    />
                    <Area
                      type="monotone"
                      dataKey={metric.gainKey}
                      fill={metric.color}
                      fillOpacity={0.1}
                      stroke="none"
                      legendType="none"
                      tooltipType="none"
                      isAnimationActive={animate}
                      animationDuration={650}
                    />
                    <Line
                      type="linear"
                      dataKey={metric.currentKey}
                      name={t('Current baseline')}
                      stroke="#b8954d"
                      strokeWidth={2}
                      strokeDasharray="6 5"
                      dot={false}
                      isAnimationActive={animate}
                      animationDuration={650}
                    />
                    <Line
                      type="monotone"
                      dataKey={metric.projectedKey}
                      name={t('Projected with strategy')}
                      stroke={metric.color}
                      strokeWidth={2.5}
                      dot={{ r: 3 }}
                      isAnimationActive={animate}
                      animationDuration={650}
                    />
                    <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
              <Typography.Text type="secondary" className="strategy-chart-caption">
                {metric.description}{' '}
                {t(
                  'Shading shows the difference from current conditions. Hover or use arrow keys to compare values.',
                )}
              </Typography.Text>
            </Card>
          );
        })}
      </section>

      <Card title={t('Technical basis')} className="strategy-table-card">
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
      </Card>

      <Card
        id="strategy-calendar-proposals"
        title={t('Events proposed to your calendar')}
        className="strategy-proposals strategy-table-card"
        extra={
          <Suspense fallback={null}>
            <EventResponseControls fieldId={field.id} />
          </Suspense>
        }
      >
        <Typography.Paragraph type="secondary" className="strategy-proposal-intro">
          {t('Strategy schedule explanation', {
            count: events.length,
            accepted: counts.accepted,
            rejected: counts.declined,
            proposed: counts.proposed,
          })}
        </Typography.Paragraph>
        <Table<PlannedEvent>
          rowKey="id"
          dataSource={events}
          pagination={false}
          scroll={{ x: 560 }}
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
                  <Typography.Paragraph type="secondary" className="strategy-event-rationale">
                    {event.duration} · {event.rationale}
                  </Typography.Paragraph>
                </div>
              ),
            },
          ]}
        />
      </Card>
    </section>
  );
}
