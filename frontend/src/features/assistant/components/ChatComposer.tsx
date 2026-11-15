import { Button, Flex, Input } from 'antd';
import { Send, Square } from 'lucide-react';
import { useState, type KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { MAX_MESSAGE_CHARS } from '../constants/assistant.constants.ts';

type ChatComposerProps = {
  isStreaming: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
  placeholder?: string;
};

export function ChatComposer({
  isStreaming,
  onSend,
  onStop,
  placeholder = 'Ask about this field…',
}: ChatComposerProps) {
  const { t } = useTranslation();
  const [text, setText] = useState('');
  const canSend = Boolean(text.trim()) && !isStreaming;

  function submit() {
    if (canSend) {
      onSend(text);
      setText('');
    }
  }

  function handleEnter(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter sends; Shift+Enter adds a line. Enter that confirms an IME choice must not send.
    if (!event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <Flex gap={8} align="flex-end">
      <Input.TextArea
        value={text}
        onChange={(event) => setText(event.target.value)}
        onPressEnter={handleEnter}
        autoSize={{ minRows: 1, maxRows: 5 }}
        maxLength={MAX_MESSAGE_CHARS}
        placeholder={t(placeholder)}
        aria-label={t(placeholder)}
      />
      <SendOrStop canSend={canSend} isStreaming={isStreaming} onSend={submit} onStop={onStop} />
    </Flex>
  );
}

type SendOrStopProps = {
  canSend: boolean;
  isStreaming: boolean;
  onSend: () => void;
  onStop: () => void;
};

function SendOrStop({ canSend, isStreaming, onSend, onStop }: SendOrStopProps) {
  const { t } = useTranslation();

  if (isStreaming) {
    return <Button icon={<Square size={16} />} onClick={onStop} aria-label={t('Stop')} />;
  }

  return (
    <Button
      type="primary"
      icon={<Send size={16} />}
      onClick={onSend}
      disabled={!canSend}
      aria-label={t('Send')}
    />
  );
}
