import type { Field } from '../../../types/fields/field.types.ts';
import type { Map as LeafletMap } from 'leaflet';
import { useRef, useState } from 'react';
import type { FieldGeoJson } from '../../../types/maps/map.types.ts';
import type { MapLayer } from '../utils/mapStyles.ts';
import { fitParcels } from '../utils/mapViewport.ts';

export function useFieldMap(geojson: FieldGeoJson, fields: Field[], locationOnly: boolean) {
  const map = useRef<LeafletMap | null>(null);
  const [selectedLayer, setLayer] = useState<MapLayer>('Crop health');
  const layer = locationOnly ? 'Field locations' : selectedLayer;
  function recenter() {
    if (map.current) {
      fitParcels(map.current, geojson, fields);
    }
  }

  return { map, setLayer, layer, recenter };
}
