import { useSuspenseQuery } from '@tanstack/react-query';
import { Card, Tooltip } from 'antd';
import { Expand } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { fieldQueries } from '../../../api/fields/fields.queries.ts';
import type { FieldGeoJson } from '../../../types/maps/map.types.ts';
import { RouterButton } from '../../../components/common/RouterButton';

import { FieldMap } from './FieldMap';

type MapCardProps = {
  expanded?: boolean;
  adding?: boolean;
};

export function MapCard({ expanded = false, adding = false }: MapCardProps) {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { data: fields } = useSuspenseQuery(fieldQueries.list());
  const fieldGeoJson: FieldGeoJson = {
    type: 'FeatureCollection',
    features: fields.map((field) => ({
      type: 'Feature',
      id: field.id,
      geometry: field.geometry,
      properties: {
        fieldId: field.id,
        catalogFieldId: field.id,
        name: field.name,
        parcelId: field.parcelId,
      },
    })),
  };

  return (
    <Card className="map-card">
      <FieldMap
        fields={fields}
        geojson={fieldGeoJson}
        onSelect={(field) => navigate(`/fields/${field.id}`)}
        adding={adding}
        locationOnly
        onAdd={() => navigate('/map/add')}
        expanded={expanded}
      />
      <Tooltip title={expanded ? t('Return to overview') : t('Expand map')}>
        <RouterButton
          className="map-expand"
          aria-label={expanded ? t('Return to overview') : t('Expand map')}
          icon={<Expand size={18} />}
          to={expanded ? '/' : '/map'}
        />
      </Tooltip>
    </Card>
  );
}
