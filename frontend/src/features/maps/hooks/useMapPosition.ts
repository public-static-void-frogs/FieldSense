import { useMap, useMapEvents } from 'react-leaflet';
import { useSearchParams } from 'react-router-dom';

export function useMapPosition() {
  const map = useMap();
  const [parameters, setParameters] = useSearchParams();
  useMapEvents({
    moveend: () => {
      const center = map.getCenter();
      const values = {
        lat: center.lat.toFixed(5),
        lon: center.lng.toFixed(5),
        zoom: String(map.getZoom()),
      };
      if (Object.entries(values).every(([key, value]) => parameters.get(key) === value)) {
        return;
      }
      const next = new URLSearchParams(parameters);
      for (const [key, value] of Object.entries(values)) {
        next.set(key, value);
      }
      setParameters(next, { replace: true, preventScrollReset: true });
    },
  });
}
