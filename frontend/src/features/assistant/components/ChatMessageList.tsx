import { Alert, Button, Spin } from 'antd';
import { Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  assistantErrorMessages,
  assistantSuggestions,
  type AssistantErrorKind,
} from '../constants/assistant.constants.ts';
import { useScrollToEnd } from '../hooks/useScrollToEnd.ts';
import type { ChatEntry } from '../utils/chatHistory.ts';
import { progressLabel } from '../utils/chatProgress.ts';

type ChatMessageListProps = {
  entries: ChatEntry[];
  activeTool: string | null;
  isStreaming: boolean;
  error: AssistantErrorKind | null;
  onAsk: (question: string) => void;
  onRetry: () => void;
  /** Welcome text and example questions; defaults to the field assistant's. */
  intro?: string;
  suggestions?: readonly string[];
};

export function ChatMessageList({
  entries,
  activeTool,
  isStreaming,
  error,
  onAsk,
  onRetry,
  intro,
  suggestions,
}: ChatMessageListProps) {
  const { t } = useTranslation();
  const end = useScrollToEnd([entries, activeTool, error]);
  const last = entries.at(-1);
  const waiting = isStreaming && (activeTool !== null || !last?.content);

  if (!entries.length) {
    return <ChatWelcome onAsk={onAsk} intro={intro} suggestions={suggestions} />;
  }

  return (
    <div className="assistant-conversation">
      <ul
        className="assistant-messages"
        role="log"
        aria-live="polite"
        aria-label={t('Conversation')}
      >
        {entries
          .filter((entry) => entry.content)
          .map((entry) => (
            <ChatBubble key={entry.id} entry={entry} />
          ))}
      </ul>
      {waiting && <ChatProgress tool={activeTool} />}
      {error && (
        <Alert
          type="warning"
          showIcon
          title={t(assistantErrorMessages[error])}
          action={
            <Button size="small" onClick={onRetry}>
              {t('Try again')}
            </Button>
          }
        />
      )}
      <div ref={end} />
    </div>
  );
}

type ChatBubbleProps = { entry: ChatEntry };

function ChatBubble({ entry }: ChatBubbleProps) {
  const { t } = useTranslation();

  if (entry.role === 'user') {
    return (
      <li className="assistant-message assistant-message--user" aria-label={t('You')}>
        <p>{entry.content}</p>
      </li>
    );
  }

  return (
    <li className="assistant-message assistant-message--assistant" aria-label={t('Assistant')}>
      <Sparkles size={18} className="ai-insight-sparkle" aria-hidden="true" />
      <p>{entry.content}</p>
    </li>
  );
}

type ChatProgressProps = { tool: string | null };

function ChatProgress({ tool }: ChatProgressProps) {
  const { t } = useTranslation();

  return (
    <div className="assistant-progress" role="status">
      <Spin size="small" />
      <span>{t(progressLabel(tool))}</span>
    </div>
  );
}

type ChatWelcomeProps = {
  onAsk: (question: string) => void;
  intro?: string;
  suggestions?: readonly string[];
};

function ChatWelcome({
  onAsk,
  intro = 'Ask about this field’s weather risk, planting timing or soil depletion.',
  suggestions = assistantSuggestions,
}: ChatWelcomeProps) {
  const { t } = useTranslation();

  return (
    <div className="assistant-welcome">
      <Sparkles size={28} className="ai-insight-sparkle" aria-hidden="true" />
      <p>{t(intro)}</p>
      <ul className="assistant-suggestions">
        {suggestions.map((question) => (
          <li key={question}>
            <Button block onClick={() => onAsk(t(question))}>
              {t(question)}
            </Button>
          </li>
        ))}
      </ul>
      <p className="assistant-disclaimer">
        {t(
          'SI answers can be wrong. Check important decisions, and ask a local agronomist about pesticide, fertilizer or irrigation doses.',
        )}
      </p>
    </div>
  );
}
