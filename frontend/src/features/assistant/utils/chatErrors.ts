import { ApiUnavailableError } from '../../../api/core/http.ts';
import { ChatInterruptedError } from '../../../api/assistant/assistant.api.ts';
import type { AssistantErrorKind } from '../constants/assistant.constants.ts';

export function classifyChatError(error: unknown): AssistantErrorKind {
  if (error instanceof ApiUnavailableError) {
    return 'unavailable';
  }
  if (error instanceof ChatInterruptedError) {
    return 'interrupted';
  }
  return 'failed';
}
