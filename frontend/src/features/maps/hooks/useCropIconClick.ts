import { useRef, type MouseEvent, type PointerEvent } from 'react';

/** Allow Leaflet to handle gestures; toggle only when the pointer interaction was a click. */
export function useCropIconClick(onToggle: () => void) {
  const origin = useRef<{ x: number; y: number; id: number } | null>(null);
  const moved = useRef(false);
  const track = (event: PointerEvent<HTMLButtonElement>) => {
    const start = origin.current;
    if (
      start &&
      start.id === event.pointerId &&
      Math.hypot(event.clientX - start.x, event.clientY - start.y) > 3
    ) {
      moved.current = true;
    }
  };

  return {
    onPointerDown: (event: PointerEvent<HTMLButtonElement>) => {
      if (!event.isPrimary || event.button !== 0) {
        return;
      }
      origin.current = { x: event.clientX, y: event.clientY, id: event.pointerId };
      moved.current = false;
    },
    onPointerMove: track,
    onPointerUp: (event: PointerEvent<HTMLButtonElement>) => {
      track(event);
      origin.current = null;
    },
    onPointerLeave: (event: PointerEvent<HTMLButtonElement>) => {
      if (origin.current && event.buttons) {
        moved.current = true;
      }
    },
    onPointerCancel: () => {
      origin.current = null;
      moved.current = true;
    },
    onClick: (event: MouseEvent<HTMLButtonElement>) => {
      if (event.detail > 0 && moved.current) {
        event.preventDefault();
        event.stopPropagation();
        return;
      }
      onToggle();
    },
  };
}
