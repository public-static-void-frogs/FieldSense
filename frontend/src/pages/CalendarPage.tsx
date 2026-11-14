import { useSuspenseQuery } from '@tanstack/react-query';
import type { TableColumnsType } from 'antd';
import { Button, Drawer, Empty, Flex, Input, Segmented, Select, Table, Tag } from 'antd';
import dayjs from 'dayjs';
import { Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { fieldQueries } from '../api/fields/fields.queries.ts';
import { planningQueries } from '../api/planning/planning.queries.ts';
import { RouterButton } from '../components/common/RouterButton';
import { CalendarDrawerContent } from '../features/planning/components/CalendarDrawerContent.tsx';
import { SystemCalendar } from '../features/planning/components/SystemCalendar';
import { planCategories } from '../features/planning/constants/planning.constants.ts';
import { useCalendarDrawer } from '../features/planning/hooks/useCalendarDrawer.ts';
import { useCalendarFilters } from '../features/planning/hooks/useCalendarFilters.ts';
import { useCalendarRoute } from '../features/planning/hooks/useCalendarRoute.ts';
import { useCalendarView } from '../features/planning/hooks/useCalendarView.ts';
import { getCalendarEvents, getEventDecision } from '../features/planning/utils/eventResponses.ts';
import { formatPlanDate } from '../features/planning/utils/planningDates.ts';
import type { PlannedEvent } from '../types/planning/planning.types.ts';

export function CalendarPage() {
  const { t } = useTranslation();
  const { data: fields } = useSuspenseQuery(fieldQueries.list());
  const { data: allEvents } = useSuspenseQuery(planningQueries.events());
  const { data: eventResponses } = useSuspenseQuery(planningQueries.responses());
  const { data: context } = useSuspenseQuery(planningQueries.context());
  const planningToday = context.today;
  const route = useCalendarRoute(planningToday);
  const filters = useCalendarFilters(getCalendarEvents(allEvents, eventResponses), route.fieldId);
  const drawer = useCalendarDrawer(route.eventId, route);
  const view = useCalendarView();
  const selectedEvents = filters.visible.filter((event) => event.date === route.selectedDate);
  const selectedEvent = allEvents.find((event) => event.id === route.eventId);
  const selectedField = fields.find((field) => field.id === selectedEvent?.fieldId);
  const columns: TableColumnsType<PlannedEvent> = [
    {
      title: t('Date'),
      dataIndex: 'date',
      width: 180,
      render: (value: string) => formatPlanDate(value),
    },
    { title: t('Field'), dataIndex: 'fieldName', width: 180 },
    {
      title: t('Planned action'),
      dataIndex: 'title',
      render: (value: string, event) => (
        <Button type="link" onClick={() => drawer.openEvent(event)}>
          {value}
        </Button>
      ),
    },
    { title: t('Type'), dataIndex: 'category', render: (value: string) => <Tag>{value}</Tag> },
    {
      title: t('Status'),
      key: 'response',
      render: (_, event) => (
        <Tag
          color={getEventDecision(event, eventResponses) === 'accepted' ? 'success' : 'processing'}
        >
          {getEventDecision(event, eventResponses) === 'accepted' ? t('Accepted') : t('Proposed')}
        </Tag>
      ),
    },
  ];

  return (
    <div className="calendar-fullscreen">
      <Flex className="calendar-toolbar" gap={10} align="center" wrap>
        <Segmented
          value={view.tab}
          onChange={view.setTab}
          options={[
            { value: 'calendar', label: t('Calendar') },
            { value: 'agenda', label: t('All actions') },
          ]}
        />
        <Select
          aria-label={t('Filter calendar by field')}
          value={route.fieldId ? String(route.fieldId) : 'all'}
          onChange={route.changeField}
          options={[
            { value: 'all', label: t('All fields') },
            ...fields.map((field) => ({ value: String(field.id), label: field.name })),
          ]}
        />
        <Select
          aria-label={t('Filter calendar by action')}
          value={filters.criteria.category}
          onChange={(category) => filters.update({ category })}
          options={['All actions', ...planCategories].map((value) => ({ value, label: t(value) }))}
        />
        <Input
          aria-label={t('Search scheduled actions')}
          prefix={<Search size={18} />}
          placeholder={t('Search actions…')}
          value={filters.criteria.query}
          onChange={(event) => filters.update({ query: event.target.value })}
          allowClear
        />
        <Button
          onClick={() => {
            filters.reset();
            view.reset();
            drawer.reset();
            route.reset();
          }}
        >
          {t('Reset view')}
        </Button>
      </Flex>
      <div className="calendar-main">
        {view.tab === 'calendar' ? (
          <SystemCalendar
            mode={view.mode}
            onModeChange={view.setMode}
            value={dayjs(route.selectedDate)}
            events={filters.visible}
            onDateSelect={drawer.selectDate}
            onPanelDateChange={route.changeDate}
            onEventSelect={drawer.openEvent}
          />
        ) : (
          <Table<PlannedEvent>
            rowKey="id"
            columns={columns}
            dataSource={filters.visible}
            scroll={{ x: 1000 }}
            pagination={{ pageSize: 8, showSizeChanger: false }}
            onRow={(event) => ({
              onClick: (click) => {
                if (!(click.target as HTMLElement).closest('a, button')) {
                  drawer.openEvent(event);
                }
              },
              className: 'clickable-row',
            })}
            locale={{
              emptyText: <Empty description={t('No planned actions match these filters.')} />,
            }}
          />
        )}
      </div>
      <Drawer
        title={selectedEvent ? t('Action details') : formatPlanDate(route.selectedDate)}
        placement="right"
        open={drawer.isOpen}
        onClose={drawer.close}
        styles={{ wrapper: { width: 'min(480px, 100vw)' } }}
        footer={
          selectedEvent && (
            <Flex gap={8}>
              <RouterButton type="primary" to={`/fields/${selectedEvent.fieldId}`}>
                {t('View field')}
              </RouterButton>
              <RouterButton to={`/fields/${selectedEvent.fieldId}/strategy`}>
                {t('View strategy')}
              </RouterButton>
            </Flex>
          )
        }
      >
        <CalendarDrawerContent
          selectedEvent={selectedEvent}
          selectedField={selectedField}
          eventId={route.eventId}
          selectedEvents={selectedEvents}
          planningToday={planningToday}
          openEvent={drawer.openEvent}
        />
      </Drawer>
    </div>
  );
}
