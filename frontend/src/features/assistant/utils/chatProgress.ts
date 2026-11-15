import { toolProgressLabels } from '../constants/assistant.constants.ts';

/** English translation key describing what the assistant is doing right now. */
export function progressLabel(tool: string | null): string {
  if (tool === null) {
    return 'Thinking…';
  }
  return toolProgressLabels[tool] ?? 'Looking up field data…';
}
