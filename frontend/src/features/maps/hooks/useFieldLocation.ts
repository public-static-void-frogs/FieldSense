import { useSuspenseQuery } from '@tanstack/react-query';
import { fieldQueries } from '../../../api/fields/fields.queries.ts';
import type { FieldGeoJson } from '../../../types/maps/map.types.ts';

export function useFieldLocation(fieldId: string): FieldGeoJson {
  const { data: field } = useSuspenseQuery(fieldQueries.byId(fieldId));
  return {
    type: 'FeatureCollection',
    features: field
      ? [
          {
            type: 'Feature',
            id: field.id,
            geometry: field.geometry,
            properties: {
              fieldId: field.id,
              catalogFieldId: field.id,
              name: field.name,
              parcelId: field.parcelId,
            },
          },
        ]
      : [],
  };
}
