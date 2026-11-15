import type { ChatMessage, ChatRole } from '../../../types/assistant/assistant.types.ts';
import { MAX_HISTORY_MESSAGES, MAX_MESSAGE_CHARS } from '../constants/assistant.constants.ts';

export type ChatEntry = {
  id: number;
  role: ChatRole;
  content: string;
  status: 'done' | 'failed';
};

/** The conversation the server needs: the server keeps no chat state, so send it all each time. */
export function buildHistory(entries: ChatEntry[]): ChatMessage[] {
  const messages = entries
    .filter((entry) => entry.status !== 'failed' && entry.content.trim())
    .map(({ role, content }) => ({ role, content: content.slice(0, MAX_MESSAGE_CHARS) }));
  const recent = messages.slice(-MAX_HISTORY_MESSAGES);
  // A conversation must start with the user's message, which trimming can break.
  while (recent.length && recent[0].role !== 'user') {
    recent.shift();
  }
  return recent;
}
