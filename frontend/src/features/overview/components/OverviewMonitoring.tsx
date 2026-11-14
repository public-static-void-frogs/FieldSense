import { ChartNoAxesCombined, Droplets, History, ThermometerSun } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { CropIcon } from '../../../components/common/CropIcon';
import type { M3CurrentRisk } from '../../../types/fields/field-insights.types.ts';
import type { Field } from '../../../types/fields/field.types.ts';
import { insightDate } from '../../fields/utils/fieldInsightFormats.ts';
import { useOverviewFieldData } from '../hooks/useOverviewFieldData.ts';
import { OverviewPanel } from './OverviewPanel';

function highestRisk(risks: M3CurrentRisk[]) {
  return risks.reduce<{ value: number; label: string } | null>((highest, risk) => {
    for (const [value, label] of [
      [risk.p_heat_overlap, 'Heat at flowering'],
      [risk.p_frost_before_maturity, 'Frost before maturity'],
    ] as const) {
      if (value != null && (highest == null || value > highest.value)) {
        highest = { value, label };
      }
    }
    return highest;
  }, null);
}

export function OverviewMonitoring({ fields }: { fields: Field[] }) {
  const { t, i18n } = useTranslation();
  const data = useOverviewFieldData(fields);
  const number = new Intl.NumberFormat(i18n.language, { maximumFractionDigits: 1 });
  const moistureNumber = new Intl.NumberFormat(i18n.language, {
    maximumFractionDigits: 3,
    minimumFractionDigits: 3,
  });
  const percent = new Intl.NumberFormat(i18n.language, {
    style: 'percent',
    maximumFractionDigits: 1,
  });
  const history = data
    .flatMap(({ field, cropHistory }) => {
      const mapped = cropHistory.data?.years
        .filter(({ crop }) => crop != null)
        .sort((a, b) => b.year - a.year);
      return mapped?.length ? [{ field, mapped }] : [];
    })
    .sort((a, b) => b.mapped[0].year - a.mapped[0].year);
  const moisture = data
    .flatMap(({ field, moisture }) => {
      const value = moisture.data?.profile_mean;
      return value == null ? [] : [{ field, value }];
    })
    .sort((a, b) => a.value - b.value);
  const climate = data
    .flatMap(({ field, climate }) => {
      const result = climate.data;
      const crop = field.crop?.toLowerCase();
      const supportedCrop = crop === 'corn' || crop === 'soybeans';
      if (!result?.ok || !supportedCrop) {
        return [];
      }
      const risk = result.risk?.now[crop];
      const peak = risk ? highestRisk([risk]) : null;
      const sowDate = result.windows?.now[`${crop}:sow`]?.date_q50;
      const sow = sowDate ? insightDate(sowDate, i18n.language) : null;
      return peak || sow ? [{ field, peak, sow }] : [];
    })
    .sort((a, b) => (b.peak?.value ?? -1) - (a.peak?.value ?? -1));
  const depletion = data
    .flatMap(({ field, depletion }) =>
      depletion?.score == null ? [] : [{ field, score: depletion.score }],
    )
    .sort((a, b) => b.score - a.score);

  function coverage(available: number, pending: boolean, errors = 0) {
    return (
      <p className="farm-muted" role="status">
        {t('Data available for {{available}} of {{total}} fields', {
          available,
          total: fields.length,
        })}
        {pending && <span> · {t('Updating…')}</span>}
        {errors > 0 && (
          <span> · {t('Data source unavailable for {{count}} fields', { count: errors })}</span>
        )}
      </p>
    );
  }

  return (
    <>
      <OverviewPanel
        title={t('Crop history')}
        icon={<History size={19} />}
        to="/fields"
        action={t('My fields')}
      >
        {coverage(
          history.length,
          data.some(({ cropHistory }) => cropHistory.isPending),
          data.filter(({ cropHistory }) => cropHistory.isError).length,
        )}
        <ul className="farm-rows farm-scroll-rows">
          {history.map(({ field, mapped }) => (
            <li key={field.id}>
              <Link className="farm-row farm-row-link" to={`/fields/${field.id}#crop-history`}>
                <CropIcon crop={field.crop} size={25} />
                <span className="farm-row-copy">
                  <strong>{field.name}</strong>
                  <small className="farm-history-latest">
                    <CropIcon crop={mapped[0].crop?.code} size={16} />
                    {mapped[0].crop?.label} · {mapped[0].year}
                  </small>
                </span>
                <span className="farm-crop-sequence" aria-hidden>
                  {mapped
                    .slice(1, 5)
                    .reverse()
                    .map(({ year, crop }) => (
                      <CropIcon key={year} crop={crop?.code} size={17} />
                    ))}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </OverviewPanel>
      <OverviewPanel
        title={t('Soil moisture')}
        icon={<Droplets size={19} />}
        to="/fields"
        action={t('My fields')}
        help={`${t('Profile mean (0–81 cm)')} · m³/m³ · ${t('Parcel reference points')}`}
      >
        {coverage(
          moisture.length,
          data.some(({ moisture }) => moisture.isPending),
          data.filter(({ moisture }) => moisture.isError).length,
        )}
        <ul className="farm-rows farm-scroll-rows">
          {moisture.map(({ field, value }) => (
            <li key={field.id}>
              <Link className="farm-row farm-row-link" to={`/fields/${field.id}#crop-history`}>
                <span className="farm-row-copy">
                  <strong>{field.name}</strong>
                  <span className="farm-metric-track" aria-hidden>
                    <span style={{ width: `${value * 100}%` }} />
                  </span>
                </span>
                <span className="farm-value">{moistureNumber.format(value)}</span>
              </Link>
            </li>
          ))}
        </ul>
      </OverviewPanel>
      <OverviewPanel
        title={t('Crop timing and climate risk')}
        icon={<ThermometerSun size={19} />}
        to="/fields"
        action={t('My fields')}
      >
        {coverage(
          climate.length,
          data.some(({ climate }) => climate.isPending),
          data.filter(({ climate }) => climate.isError).length,
        )}
        <ul className="farm-rows farm-scroll-rows">
          {climate.map(({ field, peak, sow }) => (
            <li key={field.id}>
              <Link
                className="farm-row farm-row-link"
                to={`/fields/${field.id}#crop-timing-and-climate-risk`}
              >
                <CropIcon crop={field.crop} size={24} />
                <span className="farm-row-copy">
                  <strong>{field.name}</strong>
                  <small>
                    {peak ? t(peak.label) : t('Typical sowing date')}
                    {sow && peak ? ` · ${t('Typical sowing date')}: ${sow}` : ''}
                  </small>
                </span>
                <span className="farm-value">{peak ? percent.format(peak.value) : sow}</span>
              </Link>
            </li>
          ))}
        </ul>
      </OverviewPanel>
      <OverviewPanel
        title={t('Soil depletion')}
        icon={<ChartNoAxesCombined size={19} />}
        to="/fields"
        action={t('My fields')}
      >
        {coverage(depletion.length, false)}
        {depletion.length === 0 && (
          <p className="farm-muted">
            {t('Open a field’s Crop history to run its soil assessment.')}
          </p>
        )}
        <ul className="farm-rows farm-scroll-rows">
          {depletion.map(({ field, score }) => (
            <li key={field.id}>
              <Link className="farm-row farm-row-link" to={`/fields/${field.id}#crop-history`}>
                <span className="farm-row-copy">
                  <strong>{field.name}</strong>
                </span>
                <span className="farm-value">
                  {t('{{score}} / 100', { score: number.format(score) })}
                </span>
              </Link>
            </li>
          ))}
        </ul>
        {depletion.length === 0 && (
          <ul className="farm-rows farm-scroll-rows">
            {fields.map((field) => (
              <li key={field.id}>
                <Link className="farm-row farm-row-link" to={`/fields/${field.id}#crop-history`}>
                  {field.name}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </OverviewPanel>
    </>
  );
}
