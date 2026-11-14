import { latLngBounds, type LatLngExpression } from 'leaflet';
import { useEffect, useRef } from 'react';
import { useMap } from 'react-leaflet';
import type { MapSection } from '../utils/sectionSelection.ts';

/** Fit once when a section is activated, with space reserved for its details panel. */
export function useSectionFocus(section: MapSection) {
  const map = useMap();
  const panel = useRef<HTMLElement>(null);
  const focused = useRef<string | null>(null);
  useEffect(() => {
    if (focused.current === section.id || !panel.current) {
      return;
    }
    focused.current = section.id;
    const size = map.getSize();
    const bounds = panel.current.getBoundingClientRect();
    const mobile = bounds.width > size.x * 0.7;
    const leftPanel =
      !mobile && bounds.left < map.getContainer().getBoundingClientRect().left + size.x / 2;
    const topLeft: [number, number] = [leftPanel ? bounds.width + 48 : 32, 72];
    const bottomRight: [number, number] = mobile
      ? [32, bounds.height + 40]
      : [leftPanel ? 32 : bounds.width + 48, 40];
    map.fitBounds(latLngBounds(section.outline as LatLngExpression[]), {
      paddingTopLeft: topLeft,
      paddingBottomRight: bottomRight,
      maxZoom: map.getZoom(),
      animate: true,
    });
  }, [map, section]);

  return panel;
}
