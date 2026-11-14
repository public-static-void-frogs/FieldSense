import type { ChatMessage } from '../../types/assistant/assistant.types.ts';
import { request } from '../core/http.ts';

export type ChatStreamRequest = {
  messages: ChatMessage[];
  fieldId?: string;
  locale: string;
  signal: AbortSignal;
  onDelta: (delta: string) => void;
  onTool: (tool: string) => void;
};

type ChatEvent = { delta?: string; tool?: string; done?: boolean };

// Tools can add several model rounds, so allow far longer than a normal request.
const CHAT_TIMEOUT_MS = 120_000;

export class ChatInterruptedError extends Error {
  constructor() {
    super('Assistant answer ended before completion');
    this.name = 'ChatInterruptedError';
  }
}

async function readChat(
  response: Response,
  onDelta: (delta: string) => void,
  onTool: (tool: string) => void,
) {
  const reader = response.body?.pipeThrough(new TextDecoderStream()).getReader();
  if (!reader) {
    throw new ChatInterruptedError();
  }

  let pending = '';
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        // A stream without a done event failed on the server, even if text arrived.
        throw new ChatInterruptedError();
      }
      pending += value;
      const lines = pending.split('\n');
      pending = lines.pop() ?? '';
      for (const line of lines) {
        if (!line.trim()) {
          continue;
        }
        const event: ChatEvent = JSON.parse(line);
        if (event.done) {
          return;
        }
        if (typeof event.tool === 'string') {
          onTool(event.tool);
        }
        if (typeof event.delta === 'string') {
          onDelta(event.delta);
        }
      }
    }
  } finally {
    void reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

export const assistantApi = {
  streamChat: ({ messages, fieldId, locale, signal, onDelta, onTool }: ChatStreamRequest) =>
    request(
      '/assistant/chat',
      {
        method: 'POST',
        body: JSON.stringify({ messages, field_id: fieldId, locale }),
        signal,
        timeoutMs: CHAT_TIMEOUT_MS,
      },
      (response) => readChat(response, onDelta, onTool),
    ),
};
