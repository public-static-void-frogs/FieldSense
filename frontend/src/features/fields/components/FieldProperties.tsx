import { useSuspenseQuery } from '@tanstack/react-query';
import { Card, Descriptions, Typography } from 'antd';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { fieldQueries } from '../../../api/fields/fields.queries.ts';
import type { Field } from '../../../types/fields/field.types.ts';

type FieldPropertiesProps = { field: Field };

export function FieldProperties({ field }: FieldPropertiesProps) {
  const { t } = useTranslation();
  const { data } = useSuspenseQuery(fieldQueries.properties(field.id));
  if (!data) {
    return null;
  }
  const { soil, crop } = data;
  const number = (value: number | null, unit = '') =>
    value === null
      ? t('Not supplied')
      : `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}${unit}`;

  return (
    <section aria-labelledby="field-properties-heading" className="field-properties-section">
      <Typography.Title level={3} id="field-properties-heading">
        {t('Field properties')}
      </Typography.Title>
      <div className="field-properties-stack">
        <PropertySection
          title={t('Crop & growing season')}
          items={[
            [t('Current crop'), field.crop],
            [t('Seed variety'), crop.variety],
            [t('Planting date'), field.planted],
            [t('Growth stage'), data.growthStage],
            [t('Crop establishment'), number(crop.emergence, '%')],
            [t('Plant population'), number(crop.plantDensity, ' plants/m²')],
            [t('Vegetation index (NDVI)'), number(crop.vegetationIndex)],
            [t('Target yield'), number(crop.yieldTarget, ' t/ha')],
            [t('Expected harvest'), crop.harvestWindow],
          ]}
        />
        <PropertySection
          title={t('Soil & nutrients')}
          items={[
            [t('Soil texture'), soil.soilType],
            [t('Soil pH'), number(soil.soilPh)],
            [t('Organic matter'), number(soil.organicMatter, '%')],
            [t('Available nitrogen (N)'), number(field.nitrogen, ' mg/kg')],
            [t('Phosphorus (P)'), number(soil.phosphorus, ' mg/kg')],
            [t('Potassium (K)'), number(soil.potassium, ' mg/kg')],
            [t('Soil temperature · 10 cm'), number(soil.soilTemperature, '°C')],
            [t('Salinity (electrical conductivity)'), number(soil.conductivity, ' dS/m')],
            [t('Nutrient holding capacity (CEC)'), number(soil.cationExchange, ' cmol/kg')],
            [t('Bulk density'), number(soil.bulkDensity, ' g/cm³')],
            [t('Effective rooting depth'), number(soil.rootingDepth, ' cm')],
            [t('Last soil sample'), data.lastSample],
          ]}
        />
        <PropertySection
          title={t('Land & water')}
          items={[
            [t('Field area'), number(field.area, ' ha')],
            [t('Elevation'), number(soil.elevation, ' m')],
            [t('Average slope'), number(soil.slope, '%')],
            [t('Drainage'), soil.drainage],
            [t('Irrigation system'), soil.irrigation],
            [t('Current soil moisture'), number(field.moisture, '%')],
            [t('Last irrigation'), soil.lastIrrigation],
            [t('Irrigation this season'), number(soil.waterApplied, ' mm')],
            [t('Rainfall · last 30 days'), number(soil.rainfall, ' mm')],
            [t('Available water capacity'), number(soil.waterCapacity, ' mm/m')],
            [t('Cultivation practice'), data.cultivationPractice],
            [t('Tenure'), data.tenure],
          ]}
        />
      </div>
    </section>
  );
}

type PropertySectionProps = { title: string; items: [string, ReactNode][] };

function PropertySection({ title, items }: PropertySectionProps) {
  const { t } = useTranslation();

  return (
    <Card title={title}>
      <Descriptions
        bordered
        layout="vertical"
        column={{ xs: 1, sm: 2, lg: 3 }}
        items={items.map(([label, value]) => ({
          key: label,
          label,
          children: value ?? t('Not supplied'),
        }))}
      />
    </Card>
  );
}
