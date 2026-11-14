import type { CalendarProps } from 'antd';
import { Badge, Button, Tooltip } from 'antd';
import type { Dayjs } from 'dayjs';
import { Clock3 } from 'lucide-react';
import type { CSSProperties } from 'react';
import { useTranslation } from 'react-i18next';
import type { EventResponses, PlannedEvent } from '../../../types/planning/planning.types.ts';

import { categoryColors } from '../constants/planning.constants.ts';
import { getEventDecision } from '../utils/eventResponses.ts';

type CalendarCellProps = {
  date: Dayjs;
  info: Parameters<NonNullable<CalendarProps<Dayjs>['cellRender']>>[1];
  events: PlannedEvent[];
  compact: boolean;
  eventResponses: EventResponses;
  onDateSelect: (date: string) => void;
  onEventSelect: (event: PlannedEvent) => void;
};

export function CalendarCell({
  date,
  info,
  events,
  compact,
  eventResponses,
  onDateSelect,
  onEventSelect,
}: CalendarCellProps) {
  const { t } = useTranslation();
  if (info.type === 'month') {
    const count = events.filter((event) => event.date.startsWith(date.format('YYYY-MM'))).length;
    return count ? (
      <Badge color="#476b3c" text={t('{{value0}} planned actions', { value0: count })} />
    ) : null;
  }
  if (info.type !== 'date') {
    return info.originNode;
  }
  const onDate = events.filter((event) => event.date === date.format('YYYY-MM-DD'));
  if (!onDate.length) {
    return null;
  }
  if (compact) {
    return (
      <Tooltip title={t('{{value0}} planned actions', { value0: onDate.length })}>
        <Badge count={onDate.length} color="#476b3c" />
      </Tooltip>
    );
  }

  return (
    <div className="calendar-cell-events">
      {onDate.slice(0, 2).map((event) => (
        <Tooltip
          title={`${getEventDecision(event, eventResponses) === 'accepted' ? t('Accepted') : t('Proposed')} · ${event.fieldName}: ${event.title}`}
          key={event.id}
        >
          <Button
            type="text"
            className={`calendar-cell-event ${getEventDecision(event, eventResponses) === 'proposed' ? 'calendar-event-proposed' : ''}`}
            style={{ '--event-color': categoryColors[event.category] } as CSSProperties}
            aria-label={`${event.fieldName}: ${event.title}`}
            onClick={(click) => {
              click.stopPropagation();
              onEventSelect(event);
            }}
          >
            {getEventDecision(event, eventResponses) === 'proposed' && (
              <Clock3 size={11} aria-hidden="true" />
            )}
            <span className="calendar-event-label">{`${event.category} · ${event.fieldName}`}</span>
          </Button>
        </Tooltip>
      ))}
      {onDate.length > 2 && (
        <Button
          type="text"
          size="small"
          className="calendar-more-events"
          onClick={(click) => {
            click.stopPropagation();
            onDateSelect(date.format('YYYY-MM-DD'));
          }}
        >
          {t('+{{value0}} more', { value0: onDate.length - 2 })}
        </Button>
      )}
    </div>
  );
}
