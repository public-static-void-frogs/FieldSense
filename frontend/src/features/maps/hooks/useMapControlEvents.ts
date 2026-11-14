import { DomEvent } from 'leaflet';
import { useEffect, type RefObject } from 'react';

export function useMapControlEvents(control: RefObject<HTMLElement | null>) {
  useEffect(() => {
    const element = control.current;
    if (!element) {
      return;
    }
    DomEvent.disableClickPropagation(element);
    DomEvent.disableScrollPropagation(element);
    return () => {
      DomEvent.off(element);
    };
  }, [control]);
}
