import { svg } from 'leaflet';
import { useEffect, useMemo } from 'react';

export function useMapSvgRenderer() {
  const renderer = useMemo(() => svg(), []);
  useEffect(
    () => () => {
      renderer.remove();
    },
    [renderer],
  );

  return renderer;
}
