import { useSuspenseQuery } from '@tanstack/react-query';
import { Card, Col, Descriptions, Flex, Result, Row, Space, Tag, Typography } from 'antd';
import { ArrowLeft, CalendarDays, MapPin } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router-dom';
import { fieldQueries } from '../api/fields/fields.queries.ts';
import { planningQueries } from '../api/planning/planning.queries.ts';
import { PageHeading } from '../components/common/PageHeading';
import { RouterButton } from '../components/common/RouterButton';
import { EventResponseControls } from '../features/planning/components/EventResponseControls';
import { priorityColors } from '../features/planning/utils/eventPresentation.ts';
import { formatPlanDate, getEventStatus } from '../features/planning/utils/planningDates.ts';
import { calendarEventPath } from '../features/planning/utils/planningRoutes.ts';

export function ActionDetailsPage() {
  const { eventId } = useParams<'eventId'>();
  const { t } = useTranslation();
  const { data: fields } = useSuspenseQuery(fieldQueries.list());
  const { data: planningContext } = useSuspenseQuery(planningQueries.context());
  const planningToday = planningContext.today;
  const { data: allPlanEvents } = useSuspenseQuery(planningQueries.events());
  const event = allPlanEvents.find((item) => item.id === eventId);
  const field = event && fields.find((item) => item.id === event.fieldId);

  if (!event || !field) {
    return <ActionNotFound />;
  }

  const status = getEventStatus(event.date, planningToday);

  return (
    <>
      <RouterButton
        className="section-gap"
        to={calendarEventPath(event)}
        icon={<ArrowLeft size={18} />}
      >
        {t('Back to calendar')}
      </RouterButton>
      <PageHeading
        eyebrow={t('SYSTEM ACTION PLAN')}
        title={event.title}
        description={`${field.name} · ${formatPlanDate(event.date)}`}
        actions={
          <RouterButton type="primary" to={`/fields/${field.id}`} icon={<MapPin size={18} />}>
            {t('View field')}
          </RouterButton>
        }
      />
      <Row gutter={[24, 24]}>
        <Col xs={24} xl={15}>
          <Card title={t('Action overview')} className="section-gap">
            <div className="event-response-panel">
              <Typography.Text strong>{t('Field strategy · all proposed events')}</Typography.Text>
              <EventResponseControls fieldId={event.fieldId} />
            </div>
            <Flex gap={10} wrap className="section-gap">
              <Tag>{event.category}</Tag>
              <Tag color={priorityColors[event.priority]}>{event.priority}</Tag>
              <Tag color={status === 'Due soon' ? 'warning' : 'success'}>{t(status)}</Tag>
            </Flex>
            <Typography.Paragraph>{event.description}</Typography.Paragraph>
            <Descriptions
              column={1}
              items={[
                {
                  key: 'date',
                  label: t('Scheduled date'),
                  children: (
                    <Link to={calendarEventPath(event)}>
                      <Space>
                        <CalendarDays size={18} />
                        {formatPlanDate(event.date)}
                      </Space>
                    </Link>
                  ),
                },
                { key: 'duration', label: t('Time required'), children: event.duration },
                {
                  key: 'field',
                  label: t('Field'),
                  children: t('{{value0}} · {{value1}} ha', {
                    value0: field.name,
                    value1: field.area,
                  }),
                },
                { key: 'owner', label: t('Plan maintained by'), children: t('System') },
              ]}
            />
          </Card>
          <Card title={t('Why this action is scheduled')}>
            <Typography.Paragraph className="no-margin">{event.rationale}</Typography.Paragraph>
          </Card>
        </Col>
        <Col xs={24} xl={9}>
          <Card title={t('Current field conditions')}>
            <Descriptions
              column={1}
              items={[
                { key: 'crop', label: t('Current crop'), children: field.crop },
                { key: 'health', label: t('Field health'), children: `${field.health}%` },
                { key: 'moisture', label: t('Soil moisture'), children: `${field.moisture}%` },
                {
                  key: 'nitrogen',
                  label: t('Nitrogen'),
                  children: t('{{value0}} mg/kg', { value0: field.nitrogen }),
                },
                { key: 'status', label: t('Condition'), children: field.status },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </>
  );
}

function ActionNotFound() {
  const { t } = useTranslation();

  return (
    <Result
      status="404"
      title={t('Action not found')}
      subTitle={t('This action is no longer in your field plan.')}
      extra={
        <RouterButton type="primary" to="/calendar">
          {t('Open calendar')}
        </RouterButton>
      }
    />
  );
}
