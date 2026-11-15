import { useEffect, useRef } from 'react';
import { useMap } from 'react-leaflet';
import type { Field } from '../../../types/fields/field.types.ts';
import { useMapSvgRenderer } from '../hooks/useMapSvgRenderer.ts';
import { fitParcels } from '../utils/mapViewport.ts';
import { CropArea } from './CropZones.tsx';

type SavedFieldAreasProps = { fields: Field[]; fitOnOpen: boolean };

export function SavedFieldAreas({ fields, fitOnOpen }: SavedFieldAreasProps) {
  const map = useMap();
  const renderer = useMapSvgRenderer();
  const fitted = useRef(false);
  useEffect(() => {
    if (fitOnOpen && !fitted.current) {
      fitted.current = true;
      fitParcels(
        map,
        {
          type: 'FeatureCollection',
          features: fields.map(({ geometry }) => ({ type: 'Feature', geometry, properties: null })),
        },
        fields,
      );
    }
  }, [fields, fitOnOpen, map]);

  return fields.map((field) => (
    <CropArea
      key={field.id}
      renderer={renderer}
      crop={field.crop ?? field.name}
      areaHa={field.area}
      center={field.geometry.coordinates}
      boundary={field.boundary}
      selected
    />
  ));
}
