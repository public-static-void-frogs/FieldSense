import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Collapse, Progress, Spin, Tabs, Tag, Typography } from 'antd';
import type { ReactNode } from 'react';
import { Layers3 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { fieldInsightsQueries } from '../../../api/fields/field-insights.queries.ts';
import { CropIcon } from '../../../components/common/CropIcon';
import type { SoilAssessment, SoilSignal } from '../../../types/fields/field-insights.types.ts';
import { insightNumber } from '../utils/fieldInsightFormats.ts';
import { InsightHelpLabel } from './InsightHelpLabel';
import { SoilDataView } from './SoilDataView';
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

const demandLabels = {
  high: 'High',
  moderate: 'Moderate',
  low: 'Low',
  restorative: 'Restorative',
} as const;
const repeatLabels = { repeat: 'Repeat', heavy_repeat: 'Heavy repeat' } as const;
const adviceLabels = {
  moderate: 'Review the contributing signals and keep rotating crops.',
  high: 'Consider breaking repeated cropping and confirm the result with a soil test.',
  very_high: 'Review the next crop and test the soil before planting.',
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

  return (
    <div className="field-insights-panel">
      <div className="field-insights-heading">
        <InsightHelpLabel
          label={t('Depletion score')}
          help={t(
            'This screening index uses the parcel’s reference point. Higher scores indicate more signs of depletion. A soil test is needed to measure fertility.',
          )}
        />
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
      {score === null && (
        <Alert
          type="info"
          title={t('At least half of the index weights need data to calculate an overall score.')}
        />
      )}
      {level !== 'low' && level !== 'unknown' && <p>{t(adviceLabels[level])}</p>}
      <Tabs
        items={(Object.keys(signalTitles) as SoilSignal[]).map((signal) => {
          const title = t(signalTitles[signal]);
          const value = components[signal];

          return {
            key: signal,
            label: title,
            children: (
              <div className="field-insights-panel">
                <div className="field-insights-heading">
                  {value == null && (
                    <Typography.Text type="secondary">
                      {t('No score for this signal')}
                    </Typography.Text>
                  )}
                  {value != null && (
                    <Progress
                      percent={Math.round(value * 100)}
                      format={(percent) =>
                        t('{{score}} / 100', { score: insightNumber(percent, locale) })
                      }
                      aria-label={title}
                      className="field-soil-signal-score"
                    />
                  )}
                  {drivers.includes(signal) && <Tag color="gold">{t('Driver')}</Tag>}
                </div>
                <SoilSignalDetails signal={signal} metrics={metrics} />
                {signal === 'rotation' && <RotationHistory metrics={metrics} />}
                {signal === 'greenness' && <GreennessHistory metrics={metrics} />}
              </div>
            ),
          };
        })}
      />
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

function GreennessHistory({ metrics }: { metrics: SoilAssessment['metrics'] }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const peaks = Object.entries(metrics.peak_ndvi ?? {}).reverse();
  if (!peaks.length) {
    return null;
  }

  return (
    <div>
      <SoilDataView
        title={t('Yearly satellite greenness')}
        kind="line"
        rows={peaks
          .slice()
          .reverse()
          .map(([year, ndvi]) => ({
            label: year,
            values: {
              ndvi,
              evi: metrics.peak_evi?.[year],
              scenes: metrics.peak_scene_count?.[year],
            },
          }))}
        series={[
          { key: 'ndvi', label: 'NDVI' },
          { key: 'evi', label: 'EVI' },
          { key: 'scenes', label: t('Clear scenes'), count: true },
        ]}
      >
        <div className="field-insights-peaks">
          <table className="field-insights-table">
            <thead>
              <tr>
                <th scope="col">{t('Year')}</th>
                <th scope="col">NDVI</th>
                <th scope="col">EVI</th>
                <th scope="col">{t('Clear scenes')}</th>
              </tr>
            </thead>
            <tbody>
              {peaks.map(([year, ndvi]) => (
                <tr key={year}>
                  <th scope="row">{year}</th>
                  <td>{insightNumber(ndvi, locale)}</td>
                  <td>{insightNumber(metrics.peak_evi?.[year], locale)}</td>
                  <td>{insightNumber(metrics.peak_scene_count?.[year], locale)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SoilDataView>
    </div>
  );
}

function RotationHistory({ metrics }: { metrics: SoilAssessment['metrics'] }) {
  const { t, i18n } = useTranslation();
  const marks = metrics.rotation_marks ?? [];
  const unrated = metrics.unrated_crops ?? [];
  if (!marks.length) {
    return null;
  }

  return (
    <details>
      <summary>{t('Crop demand and repetition by year')}</summary>
      <SoilDataView
        title={t('Crop demand and repetition by year')}
        rows={marks.map(({ year, crop, demand, run, mark }) => ({
          label: String(year),
          detail: mark ? `${crop} · ${t(repeatLabels[mark])}` : crop,
          values: { demand: Math.round(demand * 100), run },
        }))}
        series={[
          { key: 'demand', label: `${t('Crop demand')} (%)` },
          { key: 'run', label: t('Consecutive years'), count: true },
        ]}
      >
        <div className="field-insights-peaks">
          <table className="field-insights-table">
            <thead>
              <tr>
                <th scope="col">{t('Year')}</th>
                <th scope="col">{t('Crop')}</th>
                <th scope="col">{t('Crop demand')}</th>
                <th scope="col">{t('Consecutive years')}</th>
                <th scope="col">{t('Repetition')}</th>
              </tr>
            </thead>
            <tbody>
              {marks
                .slice()
                .reverse()
                .map(({ year, crop, demand, demand_class, run, mark }) => (
                  <tr key={year}>
                    <th scope="row">{year}</th>
                    <td>
                      <span className="field-insights-heading">
                        <CropIcon crop={crop} size={20} />
                        {crop}
                      </span>
                    </td>
                    <td>
                      {t(demandLabels[demand_class])} ·{' '}
                      {insightNumber(demand, i18n.language, 'percent')}
                    </td>
                    <td>{run}</td>
                    <td>{mark ? t(repeatLabels[mark]) : '—'}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </SoilDataView>
      {unrated.length > 0 && (
        <p>{t('A default demand rating was used for {{crops}}.', { crops: unrated.join(', ') })}</p>
      )}
    </details>
  );
}

type SoilSignalDetailsProps = {
  signal: SoilSignal;
  metrics: SoilAssessment['metrics'];
};

type SoilMetric = {
  label: string;
  value: ReactNode;
  help?: ReactNode;
};

function SoilSignalDetails({ signal, metrics }: SoilSignalDetailsProps) {
  const { t, i18n } = useTranslation();
  const number = (value: number | null) => insightNumber(value, i18n.language);
  const percent = (value: number | null) => insightNumber(value, i18n.language, 'percent');
  const percentFromWhole = (value: number | null) => {
    if (value == null) {
      return null;
    }
    return percent(value / 100);
  };
  const ratioHelp = t(
    'Compares the county yield for the crop grown that year with the state yield for the same crop and year.',
  );
  const cards: Record<SoilSignal, SoilMetric[]> = {
    rotation: [
      {
        label: t('Consecutive years'),
        value:
          metrics.years_same_crop == null ? null : (
            <>
              {number(metrics.years_same_crop)} <small>{metrics.latest_crop}</small>
            </>
          ),
        help: t(
          'The number of years in a row with the same mapped crop. A missing year breaks the streak.',
        ),
      },
      {
        label: t('Most common crop'),
        value:
          metrics.share_top_crop_5y == null ? null : (
            <>
              {percent(metrics.share_top_crop_5y)} <small>{metrics.top_crop_5y}</small>
            </>
          ),
        help: t(
          'Share of observed crop years occupied by this crop in the latest five-year window.',
        ),
      },
      {
        label: t('Average crop demand'),
        value: metrics.demand_mean_5y == null ? null : percent(metrics.demand_mean_5y),
        help: t(
          'Average of the model’s crop demand ratings over the latest five-year window. Higher ratings add more pressure to the rotation score.',
        ),
      },
      {
        label: t('Repetition'),
        value: metrics.rotation_repeat == null ? null : percent(metrics.rotation_repeat),
        help: t(
          'The rotation score’s repetition factor increases with the current streak and the crop’s demand.',
        ),
      },
      {
        label: t('Rotation load'),
        value: metrics.rotation_load == null ? null : percent(metrics.rotation_load),
        help: t(
          'The rotation score’s load factor rises when average crop demand exceeds the model’s threshold.',
        ),
      },
      {
        label: t('Crop concentration'),
        value:
          metrics.rotation_concentration == null ? null : percent(metrics.rotation_concentration),
        help: t(
          'The rotation score’s concentration factor rises when a demanding crop dominates the recent history.',
        ),
      },
    ],
    greenness: [
      {
        label: t('Annual peak NDVI change'),
        value: percentFromWhole(metrics.ndvi_trend_pct_per_yr),
        help: t(
          'Estimated yearly change in peak satellite greenness, calculated within the same crop type. Weather can also affect the trend.',
        ),
      },
      {
        label: t('Latest NDVI'),
        value: metrics.latest_ndvi == null ? null : number(metrics.latest_ndvi),
        help: (
          <span className="field-insights-help-copy">
            <span>{t('NDVI is a satellite measure of vegetation greenness.')}</span>
            {metrics.latest_vs_peak_mean != null && (
              <span>
                {t('{{value}} of the historical peak mean', {
                  value: percent(metrics.latest_vs_peak_mean),
                })}
              </span>
            )}
            <span>{t('Weather can also affect satellite greenness.')}</span>
          </span>
        ),
      },
      {
        label: t('Latest EVI'),
        value: metrics.latest_evi == null ? null : number(metrics.latest_evi),
        help: t(
          'EVI is a satellite vegetation index designed to reduce the influence of soil background and atmosphere.',
        ),
      },
      { label: t('Satellite observation date'), value: metrics.latest_greenness_date },
    ],
    soil: [
      {
        label: t('Mapped soil component'),
        value: metrics.soil_component,
        help: t('The main soil type listed for the survey map unit at this point.'),
      },
      {
        label: 'SSURGO',
        value: metrics.mukey,
        help: t('The map unit identifier in the USDA Soil Survey Geographic Database.'),
      },
      {
        label: t('Drainage class'),
        value: metrics.drainage_class,
        help: t('Describes how often and for how long the soil is naturally wet.'),
      },
      {
        label: t('Hydrologic group'),
        value: metrics.hydrologic_group,
        help: t(
          'Groups A to D describe runoff potential when the soil is wet. A has the lowest potential and D the highest. For C/D, C applies when drained and D when undrained.',
        ),
      },
      {
        label: t('Soil erodibility (K factor)'),
        value: metrics.kffact == null ? null : number(metrics.kffact),
        help: t(
          'Estimates how readily water can detach and carry soil particles. A higher K factor means the soil is more susceptible to water erosion under similar conditions.',
        ),
      },
      {
        label: t('Organic matter (top 30 cm)'),
        value: percentFromWhole(metrics.om_pct_0_30cm),
        help: t('The estimated share of organic material in the upper 30 cm of the mapped soil.'),
      },
      {
        label: t('Available water storage'),
        value:
          metrics.aws0150_cm == null
            ? null
            : t('{{value}} cm', { value: number(metrics.aws0150_cm) }),
        help: t(
          'Estimated water the soil can hold for plants in the upper 150 cm, expressed as an equivalent depth of water.',
        ),
      },
      {
        label: t('Slope'),
        value: percentFromWhole(metrics.slope_pct),
        help: t('The rise in elevation per 100 units of horizontal distance.'),
      },
    ],
    county: [
      {
        label: t('County FIPS'),
        value: metrics.county_fips,
        help: t('The five-digit identifier for a U.S. county.'),
      },
      {
        label: t('Years with yield data'),
        value: metrics.county_yield_years,
        help: t('Years with both a county and a state yield for the crop grown.'),
      },
      {
        label: t('County yield relative to state'),
        value:
          metrics.county_yield_ratio_mean == null ? null : percent(metrics.county_yield_ratio_mean),
        help: ratioHelp,
      },
      {
        label: t('Annual change in relative yield'),
        value: percentFromWhole(metrics.county_yield_ratio_slope_pct_yr),
        help: ratioHelp,
      },
    ],
  };
  const available = cards[signal].filter(({ value }) => value != null);
  if (!available.length) {
    return null;
  }

  return (
    <dl className="field-insights-grid field-soil-depletion-metrics">
      {available.map(({ label, value, help }) => (
        <div key={label}>
          <dt>
            <InsightHelpLabel label={label} help={help} />
          </dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}
