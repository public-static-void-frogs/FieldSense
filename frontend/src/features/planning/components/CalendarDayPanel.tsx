import { Empty, Tabs } from 'antd';
import { Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { ChatMessageList } from '../../assistant/components/ChatMessageList';
import type { useAssistantChat } from '../../assistant/hooks/useAssistantChat.ts';
import '../../assistant/components/FieldAssistant.css';
import type { PlannedEvent } from '../../../types/planning/planning.types.ts';
import {
  calendarAssistantIntro,
  calendarAssistantSuggestions,
} from '../constants/calendarAssistant.constants.ts';
import { PlanEventCard } from './PlanEventCard';

export type CalendarDayTab = 'assistant' | 'actions';

type CalendarDayPanelProps = {
  chat: ReturnType<typeof useAssistantChat>;
  events: PlannedEvent[];
  tab: CalendarDayTab;
  onTabChange: (tab: CalendarDayTab) => void;
  openEvent: (event: PlannedEvent) => void;
};

export function CalendarDayPanel({
  chat,
  events,
  tab,
  onTabChange,
  openEvent,
}: CalendarDayPanelProps) {
  const { t } = useTranslation();

  return (
    <Tabs
      activeKey={tab}
      onChange={(key) => onTabChange(key as CalendarDayTab)}
      items={[
        {
          key: 'assistant',
          label: (
            <span className="field-insights-crop-tab">
              <Sparkles size={16} aria-hidden="true" />
              {t('SI assistant')}
            </span>
          ),
          children: (
            <ChatMessageList
              entries={chat.entries}
              activeTool={chat.activeTool}
              isStreaming={chat.isStreaming}
              error={chat.error}
              onAsk={chat.send}
              onRetry={chat.retry}
              intro={calendarAssistantIntro}
              suggestions={calendarAssistantSuggestions}
            />
          ),
        },
        {
          key: 'actions',
          label: t('Actions'),
          children: events.length ? (
            <div className="calendar-drawer-events">
              {events.map((event) => (
                <PlanEventCard key={event.id} event={event} onSelect={() => openEvent(event)} />
              ))}
            </div>
          ) : (
            <Empty description={t('No actions for this date.')} />
          ),
        },
      ]}
    />
  );
}
