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
  const [viewport, setViewport] = useState(readViewport);
  const [revision, setRevision] = useState(0);
  useMapEvents({ moveend: () => setRevision((value) => value + 1) });
  useEffect(() => {
    const timeout = setTimeout(() => {
      const bounds = map.getBounds();
      setViewport(
        normalizeViewport(
          bounds.getWest(),
          bounds.getSouth(),
          bounds.getEast(),
          bounds.getNorth(),
          map.getZoom(),
        ),
      );
    }, 180);
    return () => clearTimeout(timeout);
  }, [map, revision]);
  useEffect(() => {
    const observer = new ResizeObserver(() => map.invalidateSize({ animate: false }));
    observer.observe(map.getContainer());
    return () => observer.disconnect();
  }, [map]);
  return useQuery(mapQueries.geojson(viewport));
}
