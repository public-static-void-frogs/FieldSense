import { divIcon, DomEvent } from 'leaflet';
import { useEffect, useMemo, useState } from 'react';

export function useSectionMarker(kind: 'add' | 'crop' = 'add') {
  const [element] = useState(() => document.createElement('div'));
  const icon = useMemo(
    () =>
      divIcon({
        className: `map-section-${kind} map-section-interactive`,
        html: element,
        iconSize: kind === 'add' ? [80, 36] : [38, 38],
        iconAnchor: kind === 'add' ? [40, 18] : [19, 19],
      }),
    [element, kind],
  );
  useEffect(() => {
    if (kind === 'crop') {
      return;
    }
    DomEvent.disableClickPropagation(element);
    DomEvent.disableScrollPropagation(element);
    return () => {
      DomEvent.off(element);
    };
  }, [element, kind]);

  return { element, icon };
}
