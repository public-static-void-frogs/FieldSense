import { useState } from 'react';

const MIN_WIDTH = 360;

function readWidth(storageKey: string, fallback: number) {
  try {
    const stored = Number(window.localStorage.getItem(storageKey));
    return stored >= MIN_WIDTH ? stored : fallback;
  } catch {
    return fallback;
  }
}

function saveWidth(storageKey: string, width: number) {
  try {
    window.localStorage.setItem(storageKey, String(Math.round(width)));
  } catch {
    // The width is only a convenience; it simply is not remembered.
  }
}

/** Props that let the user drag the edge of a right-hand Drawer; the width is remembered. */
export function useResizableDrawer(storageKey: string, defaultWidth = 480) {
  const [width, setWidth] = useState(() => readWidth(storageKey, defaultWidth));

  return {
    size: width,
    resizable: {
      onResize: setWidth,
      onResizeEnd: () => saveWidth(storageKey, width),
    },
  };
}
