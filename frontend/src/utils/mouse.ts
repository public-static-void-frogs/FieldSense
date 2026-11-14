import type { MouseEvent } from 'react';

export function isUnmodifiedPrimaryClick(event: MouseEvent) {
  return event.button === 0 && !event.metaKey && !event.ctrlKey && !event.altKey && !event.shiftKey;
}
