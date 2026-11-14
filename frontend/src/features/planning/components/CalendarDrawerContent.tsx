import { Descriptions, Empty, Flex, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import type { Field } from '../../../types/fields/field.types.ts';
import type { PlannedEvent } from '../../../types/planning/planning.types.ts';

import { priorityColors } from '../utils/eventPresentation.ts';
import { formatPlanDate, getEventStatus } from '../utils/planningDates.ts';
import { EventResponseControls } from './EventResponseControls';
import { PlanEventCard } from './PlanEventCard';

type CalendarDrawerContentProps = {
  selectedEvent?: PlannedEvent;
  selectedField?: Field;
  eventId?: string;
  selectedEvents: PlannedEvent[];
  planningToday: string;
  openEvent: (event: PlannedEvent) => void;
};

export function CalendarDrawerContent({
  selectedEvent,
  selectedField,
  eventId,
  selectedEvents,
  planningToday,
  openEvent,
}: CalendarDrawerContentProps) {
  const { t } = useTranslation();
  if (selectedEvent) {
    return (
      <CalendarActionDetails
        event={selectedEvent}
        field={selectedField}
        planningToday={planningToday}
      />
    );
  }
  if (eventId) {
    return <Empty description={t('This action is no longer in your field plan.')} />;
  }
  if (!selectedEvents.length) {
    return <Empty description={t('No actions for this date.')} />;
  }

  return (
    <div className="calendar-drawer-events">
      {selectedEvents.map((event) => (
        <PlanEventCard key={event.id} event={event} onSelect={() => openEvent(event)} />
      ))}
    </div>
  );
}

type CalendarActionDetailsProps = {
  event: PlannedEvent;
  field?: Field;
  planningToday: string;
};

function CalendarActionDetails({ event, field, planningToday }: CalendarActionDetailsProps) {
  const { t } = useTranslation();

  return (
    <>
      <div className="event-response-panel">
        <Typography.Text strong>{t('Field strategy · all proposed events')}</Typography.Text>
        <EventResponseControls fieldId={event.fieldId} />
      </div>
      <Flex gap={8} wrap className="section-gap">
        <Tag>{event.category}</Tag>
        <Tag color={priorityColors[event.priority]}>{event.priority}</Tag>
        <Tag>{t(getEventStatus(event.date, planningToday))}</Tag>
      </Flex>
      <Typography.Title level={3}>{event.title}</Typography.Title>
      <Typography.Paragraph>{event.description}</Typography.Paragraph>
      <Descriptions
        column={1}
        items={[
          {
            key: 'date',
            label: t('Scheduled date'),
            children: formatPlanDate(event.date),
          },
          { key: 'field', label: t('Field'), children: event.fieldName },
          { key: 'duration', label: t('Time required'), children: event.duration },
          { key: 'owner', label: t('Maintained by'), children: t('System') },
        ]}
      />
      <Typography.Title level={5}>{t('Why this action is scheduled')}</Typography.Title>
      <Typography.Paragraph>{event.rationale}</Typography.Paragraph>
      {field && <CalendarFieldConditions field={field} />}
    </>
  );
}

type CalendarFieldConditionsProps = {
  field: Field;
};

function CalendarFieldConditions({ field }: CalendarFieldConditionsProps) {
  const { t } = useTranslation();

  return (
    <>
      <Typography.Title level={5}>{t('Current field conditions')}</Typography.Title>
      <Descriptions
        column={1}
        items={[
          { key: 'crop', label: t('Crop'), children: field.crop },
          {
            key: 'area',
            label: t('Area'),
            children: t('{{value0}} ha', { value0: field.area }),
          },
          {
            key: 'health',
            label: t('Crop health'),
            children: `${field.health}%`,
          },
          {
            key: 'moisture',
            label: t('Soil moisture'),
            children: `${field.moisture}%`,
          },
          {
            key: 'nitrogen',
            label: t('Nitrogen'),
            children: t('{{value0}} mg/kg', { value0: field.nitrogen }),
          },
          { key: 'status', label: t('Condition'), children: field.status },
        ]}
      />
    </>
  );
}
