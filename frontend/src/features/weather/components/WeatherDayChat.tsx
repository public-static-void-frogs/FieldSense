import { Button } from 'antd';
import { MessageCircleQuestion } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChatComposer } from '../../assistant/components/ChatComposer';
import { ChatMessageList } from '../../assistant/components/ChatMessageList';
import { useAssistantChat } from '../../assistant/hooks/useAssistantChat.ts';
import '../../assistant/components/FieldAssistant.css';
import {
  weatherChatPlaceholder,
  weatherChatSuggestions,
} from '../constants/weatherChat.constants.ts';

type WeatherDayChatProps = { date: string; locale: string; fieldId?: string };

/**
 * Follow-up questions about the open forecast day. The short summary above stays as it is; this
 * chat can use the assistant's tools, so it can go beyond the summary. The parent is keyed by
 * day, so each day starts a new conversation.
 */
export function WeatherDayChat({ date, locale, fieldId }: WeatherDayChatProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const chat = useAssistantChat(fieldId, locale, { weatherDate: date });

  if (!open) {
    return (
      <Button
        className="weather-day-chat-toggle"
        icon={<MessageCircleQuestion size={18} />}
        onClick={() => setOpen(true)}
      >
        {t('Ask a follow-up')}
      </Button>
    );
  }

  return (
    <div className="weather-day-chat">
      {chat.entries.length > 0 ? (
        <ChatMessageList
          entries={chat.entries}
          activeTool={chat.activeTool}
          isStreaming={chat.isStreaming}
          error={chat.error}
          onAsk={chat.send}
          onRetry={chat.retry}
        />
      ) : (
        <ul className="assistant-suggestions">
          {weatherChatSuggestions.map((question) => (
            <li key={question}>
              <Button block onClick={() => chat.send(t(question))}>
                {t(question)}
              </Button>
            </li>
          ))}
        </ul>
      )}
      <ChatComposer
        isStreaming={chat.isStreaming}
        onSend={chat.send}
        onStop={chat.stop}
        placeholder={weatherChatPlaceholder}
      />
    </div>
  );
}
