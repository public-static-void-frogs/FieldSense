import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Card, Collapse, Progress, Spin, Tag, Typography } from 'antd';
import { Layers3 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { fieldInsightsQueries } from '../../../api/fields/field-insights.queries.ts';
import type { SoilAssessment, SoilSignal } from '../../../types/fields/field-insights.types.ts';
import { insightNumber } from '../utils/fieldInsightFormats.ts';
import './FieldInsights.css';

const signalTitles = {
  rotation: 'Crop rotation',
  greenness: 'Satellite greenness',
  soil: 'Mapped soil',
  county: 'County yield',
} as const;

const levels = {
  low: { label: 'Low', color: 'green' },
  moderate: { label: 'Moderate', color: 'gold' },
  high: { label: 'High', color: 'orange' },
  very_high: { label: 'Very high', color: 'red' },
  unknown: { label: 'Insufficient data', color: 'default' },
} as const;

const noteText: Record<string, string> = {
  crop_history_unavailable: 'USDA crop history is temporarily unavailable.',
  rotation_insufficient_history: 'Too few recent crop years to assess rotation.',
  greenness_insufficient_years:
    'The greenness trend needs at least four usable years of the same crop.',
  greenness_partial: 'Some satellite observations were unavailable during this calculation.',
  greenness_unavailable: 'Historical satellite observations are temporarily unavailable.',
  soil_not_mapped: 'No USDA soil survey data was found at this location.',
  soil_insufficient_data: 'The mapped soil has too few measurements to score.',
  soil_unavailable: 'Mapped soil data is temporarily unavailable.',
  county_not_configured: 'County yield data is unavailable.',
  county_unavailable: 'County yield data is temporarily unavailable.',
  county_insufficient_years:
    'Too few years of county and state yields were available for comparison.',
  analysis_unavailable: 'The soil analysis is temporarily unavailable.',
};

type FieldSoilDepletionProps = { fieldId: string; part: number; geometryKey: string };

export function FieldSoilDepletion(props: FieldSoilDepletionProps) {
  const { t } = useTranslation();

  return (
    <Collapse
      className="field-insights-soil"
      destroyOnHidden
      items={[
        {
          key: 'soil',
          label: t('Soil depletion'),
          extra: <Layers3 size={17} aria-hidden />,
          children: <SoilDepletionPanel {...props} />,
        },
      ]}
    />
  );
}

function SoilDepletionPanel({ fieldId, part, geometryKey }: FieldSoilDepletionProps) {
  const { t } = useTranslation();
  const query = useQuery(fieldInsightsQueries.soil(fieldId, part, geometryKey));

  if (query.isError) {
    return (
      <Alert
        type="error"
        title={t('Could not load the soil assessment.')}
        action={<Button onClick={() => void query.refetch()}>{t('Retry')}</Button>}
      />
    );
  }
  if (!query.data?.assessment) {
    return (
      <div className="field-insights-heading" role="status">
        <Spin size="small" />
        <span>
          {query.data?.status === 'busy'
            ? t('Waiting for other soil assessments to finish…')
            : t('Checking crop history, soil maps, and historical satellite imagery…')}
        </span>
      </div>
    );
  }

  return <SoilAssessmentResults assessment={query.data.assessment} />;
}

type SoilAssessmentResultsProps = { assessment: SoilAssessment };

function SoilAssessmentResults({ assessment }: SoilAssessmentResultsProps) {
  const { t, i18n } = useTranslation();
  const { score, level, coverage, components, drivers, metrics, notes } = assessment;
  const locale = i18n.language;
  const peaks = Object.entries(metrics.peak_ndvi ?? {}).reverse();

  return (
    <div className="field-insights-panel">
      <div className="field-insights-heading">
        {score !== null && (
          <strong>{t('{{score}} / 100', { score: insightNumber(score, locale) })}</strong>
        )}
        <Tag color={levels[level].color}>{t(levels[level].label)}</Tag>
        <span>
          {t('{{coverage}} of the index weights have data', {
            coverage: insightNumber(coverage, locale, 'percent'),
          })}
        </span>
      </div>
      <Typography.Text type="secondary">
        {t(
          'This screening index uses the parcel’s reference point. Higher scores indicate more signs of depletion. A soil test is needed to measure fertility.',
        )}
      </Typography.Text>
      {score === null && (
        <Alert
          type="info"
          title={t('At least half of the index weights need data to calculate an overall score.')}
        />
      )}
      <div className="field-insights-grid field-insights-signals">
        {Object.entries(signalTitles).map(([key, title]) => {
          const signal = key as SoilSignal;
          const value = components[signal];

          return (
            <Card size="small" className="field-insights-metric" key={key}>
              <div className="field-insights-heading">
                <strong className="field-insights-signal-label">{t(title)}</strong>
                {drivers.includes(signal) && <Tag color="gold">{t('Driver')}</Tag>}
              </div>
              {value != null && (
                <Progress
                  percent={Math.round(value * 100)}
                  showInfo={false}
                  aria-label={t(title)}
                />
              )}
              <SoilSignalDetails signal={signal} metrics={metrics} available={value != null} />
            </Card>
          );
        })}
      </div>
      {peaks.length > 0 && (
        <details>
          <summary>{t('Yearly satellite greenness')}</summary>
          <div className="field-insights-peaks">
            <table className="field-insights-table">
              <thead>
                <tr>
                  <th scope="col">{t('Year')}</th>
                  <th scope="col">NDVI</th>
                  <th scope="col">EVI</th>
                </tr>
              </thead>
              <tbody>
                {peaks.map(([year, ndvi]) => (
                  <tr key={year}>
                    <th scope="row">{year}</th>
                    <td>{insightNumber(ndvi, locale)}</td>
                    <td>{insightNumber(metrics.peak_evi?.[year], locale)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
      {notes.length > 0 && (
        <ul className="field-insights-notes field-insights-muted">
          {notes.map((note) => (
            <li key={note}>{t(noteText[note] ?? 'Some inputs were unavailable.')}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

type SoilSignalDetailsProps = {
  signal: SoilSignal;
  metrics: SoilAssessment['metrics'];
  available: boolean;
};

function SoilSignalDetails({ signal, metrics, available }: SoilSignalDetailsProps) {
  const { t, i18n } = useTranslation();
  const number = (value: number | null) => insightNumber(value, i18n.language);
  const percent = (value: number) => insightNumber(value, i18n.language, 'percent');

  return (
    <>
      {!available && (
        <Typography.Text type="secondary">{t('No score for this signal')}</Typography.Text>
      )}
      {signal === 'rotation' && metrics.years_same_crop !== null && (
        <span>
          {t('Latest streak: {{crop}} (years: {{count}})', {
            crop: metrics.latest_crop,
            count: metrics.years_same_crop,
          })}
        </span>
      )}
      {signal === 'rotation' && metrics.share_top_crop_5y !== null && (
        <span>
          {t('{{crop}} in {{share}} of the last five years with data', {
            crop: metrics.top_crop_5y,
            share: percent(metrics.share_top_crop_5y),
          })}
        </span>
      )}
      {signal === 'greenness' && metrics.ndvi_trend_pct_per_yr !== null && (
        <span>
          {t('Peak NDVI change of {{change}} per year', {
            change: percent(metrics.ndvi_trend_pct_per_yr / 100),
          })}
        </span>
      )}
      {signal === 'greenness' && available && (
        <small>{t('Weather can also affect satellite greenness.')}</small>
      )}
      {signal === 'soil' && metrics.om_pct_0_30cm !== null && (
        <span>
          {t('{{value}} organic matter in the top 30 cm', {
            value: percent(metrics.om_pct_0_30cm / 100),
          })}
        </span>
      )}
      {signal === 'soil' && metrics.aws0150_cm !== null && (
        <span>
          {t('{{value}} cm of available water storage', { value: number(metrics.aws0150_cm) })}
        </span>
      )}
      {signal === 'soil' && metrics.slope_pct !== null && (
        <span>{t('{{value}} slope', { value: percent(metrics.slope_pct / 100) })}</span>
      )}
      {signal === 'county' && metrics.county_yield_ratio_mean !== null && (
        <span>
          {t('County yields averaged {{value}} of state yields', {
            value: percent(metrics.county_yield_ratio_mean),
          })}
        </span>
      )}
      {signal === 'county' && metrics.county_yield_ratio_slope_pct_yr !== null && (
        <span>
          {t('County-to-state yield ratio changed {{value}} per year', {
            value: percent(metrics.county_yield_ratio_slope_pct_yr / 100),
          })}
        </span>
      )}
    </>
  );
}
