import { useEffect, useRef } from 'react';

/** Keep the newest content in view: scroll an end marker into view when `watch` changes. */
export function useScrollToEnd(watch: unknown[]) {
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // The effect must not return anything: React treats a returned value as its cleanup function.
    end.current?.scrollIntoView({ block: 'end' });
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, watch);

  return end;
}
