import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useAssistantChat } from '../../assistant/hooks/useAssistantChat.ts';
import { calendarAssistantPrompt } from '../constants/calendarAssistant.constants.ts';
import { formatPlanDate } from '../utils/planningDates.ts';

type CalendarAssistantOptions = {
  date: string;
  fieldId: string | undefined;
  open: boolean;
  hasEvents: boolean;
};

/**
 * A chat about the selected calendar day. Opening a day starts a new conversation that explains
 * it; follow-up questions continue it and can use the assistant's tools.
 */
export function useCalendarAssistant({ date, fieldId, open, hasEvents }: CalendarAssistantOptions) {
  const { t, i18n } = useTranslation();
  const chat = useAssistantChat(fieldId, i18n.resolvedLanguage ?? 'en', { calendarDate: date });
  const started = useRef<string | null>(null);
  const { restart, clear } = chat;

  useEffect(() => {
    if (!open) {
      started.current = null;
      return;
    }
    const key = `${date}|${fieldId ?? ''}`;
    if (started.current === key) {
      return;
    }
    started.current = key;
    if (hasEvents) {
      restart(t(calendarAssistantPrompt, { date: formatPlanDate(date) }));
    } else {
      clear();
    }
  }, [open, date, fieldId, hasEvents, restart, clear, t]);

  return chat;
}
