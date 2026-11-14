import { Layers3, Map as MapIcon, Sprout } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router-dom';
import { CropIcon } from '../../../components/common/CropIcon';
import type { Field } from '../../../types/fields/field.types.ts';
import type { FieldGeoJson } from '../../../types/maps/map.types.ts';
import { FieldStatus } from '../../fields/components/FieldStatus';
import { FieldMap } from '../../maps/components/FieldMap';
import { chartColors } from '../constants/overview.constants.ts';
import { OverviewPanel } from './OverviewPanel';

export function OverviewInventory({ fields }: { fields: Field[] }) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const number = new Intl.NumberFormat(i18n.language, { maximumFractionDigits: 1 });
  const percent = new Intl.NumberFormat(i18n.language, { style: 'percent' });
  const areaLabel = (area: number) => t('{{value0}} ha', { value0: number.format(area) });
  const byCrop = new Map<string | null, { area: number; fields: number }>();
  const geojson: FieldGeoJson = {
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
  for (const field of fields) {
    const crop = field.crop?.trim() || null;
    const group = byCrop.get(crop) ?? { area: 0, fields: 0 };
    byCrop.set(crop, { area: group.area + field.area, fields: group.fields + 1 });
  }
  const total = fields.reduce((sum, { area }) => sum + area, 0);
  const cropGroups = [...byCrop].sort((a, b) => b[1].area - a[1].area);
  const measured = fields.filter(({ status }) => status != null).length;
  const statusRank = { Critical: 0, 'Needs attention': 1, Healthy: 2, Unmeasured: 3 };
  const ordered = fields
    .slice()
    .sort(
      (a, b) =>
        (statusRank[a.status ?? 'Unmeasured'] ?? 3) - (statusRank[b.status ?? 'Unmeasured'] ?? 3) ||
        a.name.localeCompare(b.name),
    );

  const soilFields = fields.filter(({ properties }) => properties?.soil != null);
  const soilSummaries = [
    { label: 'Mean soil pH', read: (field: Field) => field.properties?.soil.soilPh, unit: '' },
    {
      label: 'Mean organic matter',
      read: (field: Field) => field.properties?.soil.organicMatter,
      unit: '%',
    },
  ].map(({ label, read, unit }) => {
    const values = soilFields.flatMap((field) => {
      const value = read(field);
      return value == null ? [] : [value];
    });
    const value = values.length
      ? number.format(values.reduce((sum, v) => sum + v, 0) / values.length) + unit
      : '—';
    return { label, value, count: values.length };
  });

  return (
    <>
      <OverviewPanel
        title={t('Field map')}
        icon={<MapIcon size={19} />}
        to="/map"
        action={t('Explore map')}
        className="farm-panel-wide farm-map-panel"
      >
        <FieldMap
          fields={fields}
          geojson={geojson}
          locationOnly
          hideControls
          permanentLabels={false}
          scrollWheelZoom={false}
          adding={false}
          onSelect={(field) => navigate(`/fields/${field.id}`)}
          onAdd={() => navigate('/map/add')}
        />
      </OverviewPanel>
      <OverviewPanel
        title={t('Crop mix')}
        icon={<Sprout size={19} />}
        to="/fields"
        action={t('My fields')}
      >
        <div className="farm-allocation" aria-hidden>
          {cropGroups.map(([crop, group], index) => (
            <span
              key={crop ?? ''}
              style={{
                flexGrow: total > 0 ? group.area : group.fields,
                background: chartColors[index % chartColors.length],
              }}
            />
          ))}
        </div>
        <ul className="farm-rows farm-scroll-rows">
          {cropGroups.map(([crop, group], index) => (
            <li key={crop ?? ''} className="farm-row">
              <span
                className="farm-swatch"
                style={{ background: chartColors[index % chartColors.length] }}
                aria-hidden
              />
              <CropIcon crop={crop} size={24} />
              <span className="farm-row-copy">
                <strong>{crop ?? t('Not supplied')}</strong>
                <small>{t('Field count: {{count}}', { count: group.fields })}</small>
              </span>
              <span className="farm-value">
                {areaLabel(group.area)}
                {total > 0 && <small>{percent.format(group.area / total)}</small>}
              </span>
            </li>
          ))}
        </ul>
      </OverviewPanel>
      <OverviewPanel
        title={t('Field conditions')}
        icon={<Layers3 size={19} />}
        to="/fields"
        action={t('View all fields')}
      >
        <p className="farm-muted">
          {t('Status available for {{available}} of {{total}} fields', {
            available: measured,
            total: fields.length,
          })}
        </p>
        <ul className="farm-rows farm-scroll-rows">
          {ordered.map((field) => (
            <li key={field.id}>
              <Link to={`/fields/${field.id}`} className="farm-row farm-row-link">
                <CropIcon crop={field.crop} size={28} />
                <span className="farm-row-copy">
                  <strong>{field.name}</strong>
                  <small>
                    {field.crop ?? t('Not supplied')} · {areaLabel(field.area)}
                  </small>
                </span>
                <FieldStatus status={field.status} />
              </Link>
            </li>
          ))}
        </ul>
        {soilFields.length > 0 && (
          <dl className="farm-soil-metrics">
            {soilSummaries.map(({ label, value, count }) => (
              <div key={label}>
                <dt>{t(label)}</dt>
                <dd>{value}</dd>
                <dd>
                  <small>{t('Fields with readings: {{count}}', { count })}</small>
                </dd>
              </div>
            ))}
          </dl>
        )}
      </OverviewPanel>
    </>
  );
}
