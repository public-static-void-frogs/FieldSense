import type { Map as LeafletMap } from 'leaflet';
import { useCallback, useEffect, useRef, useState } from 'react';
import type { LocationPoint } from '../../../types/maps/map.types.ts';
import { locationPoint } from '../utils/location.ts';

type LocationPickerOptions = {
  value?: LocationPoint;
  autoLocate?: boolean;
  onChange?: (point: LocationPoint) => void;
};

export function useLocationPicker({ value, onChange, autoLocate = true }: LocationPickerOptions) {
  const map = useRef<LeafletMap | null>(null);
  const callback = useRef(onChange);
  const initialValue = useRef(value);
  const requestId = useRef(0);
  const [status, setStatus] = useState<'idle' | 'locating' | 'denied' | 'unavailable' | 'error'>(
    'idle',
  );
  useEffect(() => {
    callback.current = onChange;
  }, [onChange]);

  const locate = useCallback(() => {
    const id = ++requestId.current;
    if (!navigator.geolocation) {
      setStatus('unavailable');
      return;
    }
    setStatus('locating');
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        if (id !== requestId.current) {
          return;
        }
        setStatus('idle');
        callback.current?.(locationPoint(coords.latitude, coords.longitude));
      },
      (error) => {
        if (id !== requestId.current) {
          return;
        }
        setStatus(error.code === 1 ? 'denied' : 'error');
      },
      { enableHighAccuracy: false, timeout: 10_000, maximumAge: 60_000 },
    );
  }, []);

  const cancelLocation = useCallback(() => {
    requestId.current++;
  }, []);

  useEffect(() => {
    if (autoLocate && !initialValue.current) {
      locate();
    }
    return cancelLocation;
  }, [autoLocate, locate, cancelLocation]);

  const select = useCallback((point: LocationPoint) => {
    requestId.current++;
    setStatus('idle');
    callback.current?.(point);
  }, []);

  function selectCenter() {
    const center = map.current?.getCenter();
    if (center) {
      select(locationPoint(center.lat, center.lng));
    }
  }

  return { map, status, locate, select, selectCenter };
}
