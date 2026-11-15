import { useMutation } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { assistantMutations } from '../../../api/assistant/assistant.mutations.ts';
import type { AssistantErrorKind } from '../constants/assistant.constants.ts';
import { buildHistory, type ChatEntry } from '../utils/chatHistory.ts';
import { classifyChatError } from '../utils/chatErrors.ts';

export function useAssistantChat(
  fieldId: string | undefined,
  locale: string,
  calendarDate?: string,
) {
  const chat = useMutation(assistantMutations.chat());
  const [entries, setEntries] = useState<ChatEntry[]>([]);
  const [activeTool, setActiveTool] = useState<string | null>(null);
  const [error, setError] = useState<AssistantErrorKind | null>(null);
  const controller = useRef<AbortController | null>(null);
  const nextId = useRef(1);

  useEffect(() => () => controller.current?.abort(), []);

  async function ask(previous: ChatEntry[], text: string) {
    const question: ChatEntry = {
      id: nextId.current++,
      role: 'user',
      content: text,
      status: 'done',
    };
    const answerId = nextId.current++;
    const answer: ChatEntry = { id: answerId, role: 'assistant', content: '', status: 'done' };
    const abort = new AbortController();
    controller.current = abort;
    setEntries([...previous, question, answer]);
    setError(null);
    setActiveTool(null);

    const update = (change: (entry: ChatEntry) => ChatEntry) =>
      setEntries((current) =>
        current.map((entry) => (entry.id === answerId ? change(entry) : entry)),
      );

    try {
      await chat.mutateAsync({
        messages: buildHistory([...previous, question]),
        fieldId,
        calendarDate,
        locale,
        signal: abort.signal,
        onDelta: (delta) => {
          setActiveTool(null);
          update((entry) => ({ ...entry, content: entry.content + delta }));
        },
        onTool: setActiveTool,
      });
    } catch (failure) {
      if (!abort.signal.aborted) {
        setError(classifyChatError(failure));
        update((entry) => ({ ...entry, status: 'failed' }));
      }
    } finally {
      setActiveTool(null);
      // Drop an answer that never got any text; keep partial text so nothing the user saw vanishes.
      setEntries((current) =>
        current.filter((entry) => entry.id !== answerId || entry.content.trim()),
      );
    }
  }

  function send(text: string) {
    const content = text.trim();
    if (content && !chat.isPending) {
      void ask(entries, content);
    }
  }

  function retry() {
    const lastQuestion = entries.findLastIndex((entry) => entry.role === 'user');
    if (lastQuestion >= 0 && !chat.isPending) {
      void ask(entries.slice(0, lastQuestion), entries[lastQuestion].content);
    }
  }

  function stop() {
    controller.current?.abort();
  }

  /** Drop the conversation and start a new one with this question (stops any running answer). */
  function restart(text: string) {
    controller.current?.abort();
    void ask([], text);
  }

  function clear() {
    controller.current?.abort();
    setEntries([]);
    setError(null);
    setActiveTool(null);
  }

  return {
    entries,
    activeTool,
    error,
    isStreaming: chat.isPending,
    send,
    retry,
    stop,
    restart,
    clear,
  };
}
