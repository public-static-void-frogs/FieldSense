import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useMap, useMapEvents } from 'react-leaflet';
import { mapQueries } from '../../../api/maps/maps.queries.ts';
import { normalizeViewport } from '../utils/catalogViewport.ts';

export function useCatalogViewport() {
  const map = useMap();
  const readViewport = () => {
    const bounds = map.getBounds();
    return normalizeViewport(
      bounds.getWest(),
      bounds.getSouth(),
      bounds.getEast(),
      bounds.getNorth(),
      map.getZoom(),
    );
  };
  const [requested, setRequested] = useState(() => ({ viewport: readViewport(), revision: 0 }));
  const [revision, setRevision] = useState(0);
  useMapEvents({ moveend: () => setRevision((value) => value + 1) });
  useEffect(() => {
    const timeout = setTimeout(() => {
      const bounds = map.getBounds();
      setRequested({
        revision,
        viewport: normalizeViewport(
          bounds.getWest(),
          bounds.getSouth(),
          bounds.getEast(),
          bounds.getNorth(),
          map.getZoom(),
        ),
      });
    }, 180);
    return () => clearTimeout(timeout);
  }, [map, revision]);
  useEffect(() => {
    const observer = new ResizeObserver(() => map.invalidateSize({ animate: false }));
    observer.observe(map.getContainer());
    return () => observer.disconnect();
  }, [map]);
  const query = useQuery(mapQueries.geojson(requested.viewport));
  const canSelect =
    requested.revision === revision && query.data?.mode === 'fields' && !query.isPlaceholderData;

  return { query, canSelect };
}
