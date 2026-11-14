import { useEffect, useRef } from 'react';

/** Keep the newest content in view: scroll an end marker into view when `watch` changes. */
export function useScrollToEnd(watch: unknown[]) {
  const end = useRef<HTMLDivElement>(null);

  // oxlint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => end.current?.scrollIntoView({ block: 'end' }), watch);

  return end;
}
