import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Card, Empty, Skeleton, Tabs, Timeline } from 'antd';
import { Droplets } from 'lucide-react';
import type { CSSProperties, ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { fieldInsightsQueries } from '../../../api/fields/field-insights.queries.ts';
import type {
  M3Crop,
  M3CurrentRisk,
  M3Delay,
  M3Insights,
  M3Scenario,
  M3Water,
  M3Window,
} from '../../../types/fields/field-insights.types.ts';
import { CropIcon } from '../../../components/common/CropIcon';
import type { Field } from '../../../types/fields/field.types.ts';
import { insightDate, insightNumber } from '../utils/fieldInsightFormats.ts';
import { InsightHelpLabel } from './InsightHelpLabel';
import './FieldInsights.css';

const crops = { corn: 'Corn', soybeans: 'Soybeans' } as const;
const scenarios = { ssp245: 'Intermediate emissions', ssp585: 'High emissions' } as const;
const scenarioColors = {
  ssp245: { marker: 'var(--field-insights-green)', range: 'var(--field-insights-green-range)' },
  ssp585: { marker: 'var(--field-insights-risk-red)', range: '#edb4a8' },
} as const;
const frosts = {
  last_spring_frost: 'Last spring frost',
  first_autumn_frost: 'First autumn frost',
} as const;
const stages = {
  first_ready: 'First workable planting day',
  sow: 'Sowing',
  flower: 'Flowering',
  mature: 'Maturity',
} as const;

type FieldM3InsightsProps = { field: Field };

export function FieldM3Insights({ field }: FieldM3InsightsProps) {
  const { t, i18n } = useTranslation();
  const query = useQuery(
    fieldInsightsQueries.m3(field.id, JSON.stringify(field.geometry.coordinates)),
  );
  const insights = query.data;
  let content = <Skeleton active paragraph={{ rows: 2 }} />;
  if (query.isError) {
    content = (
      <Alert
        type="error"
        title={t('Could not load crop timing and risk.')}
        action={<Button onClick={() => void query.refetch()}>{t('Retry')}</Button>}
      />
    );
  } else if (insights?.ok) {
    content = <M3Results insights={insights} />;
  } else if (insights) {
    content = (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={t('This field is outside the crop timing model’s coverage.')}
      />
    );
  }

  const title = t('Crop timing and climate risk');
  const match = insights?.ok ? insights.match : null;
  let locationHelp;
  if (match) {
    locationHelp =
      match.level === 'field'
        ? t('Uses an indexed field {{distance}} km away', {
            distance: insightNumber(match.distance_km, i18n.language),
          })
        : t('Uses a regional weather cell');
  }

  return <Card title={<InsightHelpLabel label={title} help={locationHelp} />}>{content}</Card>;
}

type M3ResultsProps = { insights: M3Insights };

function M3Results({ insights }: M3ResultsProps) {
  const { t } = useTranslation();
  const current = insights.windows?.now;
  const frostEntries = Object.entries(frosts)
    .map(([key, label]) => ({ key, label, window: current?.[key] }))
    .filter(({ window }) => window?.date_q50);

  return (
    <div className="field-insights-panel">
      {insights.match?.level === 'field' && insights.match.awc_mm != null && (
        <M3WaterCapacity value={insights.match.awc_mm} median={insights.match.reference_awc_mm} />
      )}
      {frostEntries.length > 0 && <M3DateTimeline entries={frostEntries} />}
      <Tabs
        items={(Object.keys(crops) as M3Crop[]).map((crop) => ({
          key: crop,
          label: (
            <span className="field-insights-crop-tab">
              <CropIcon crop={crops[crop]} />
              {t(crops[crop])}
            </span>
          ),
          children: <M3CropPanel crop={crop} insights={insights} />,
        }))}
      />
      {insights.warnings.length > 0 && (
        <details>
          <summary>{t('Model data notes')}</summary>
          <ul className="field-insights-notes">
            {insights.warnings.map((warning) => (
              <li key={warning}>{t(warning, { defaultValue: warning })}</li>
            ))}
          </ul>
        </details>
      )}
      <small>{t('Window Forecaster (ChronoShift + Fallow-Zero)')}</small>
    </div>
  );
}

type M3WaterCapacityProps = { value: number; median: number | null | undefined };

function M3WaterCapacity({ value, median }: M3WaterCapacityProps) {
  const { t, i18n } = useTranslation();
  const formatMm = (amount: number) =>
    t('{{value}} mm', { value: insightNumber(amount, i18n.language) });
  const difference = median == null ? 0 : Math.round((value - median) * 10) / 10;
  let comparison = t('About the same as the local median.');
  if (difference !== 0) {
    comparison = t(
      difference > 0 ? '{{value}} above the local median.' : '{{value}} below the local median.',
      { value: formatMm(Math.abs(difference)) },
    );
  }

  return (
    <div className="field-insights-water-capacity">
      <h3>
        <Droplets size={18} aria-hidden="true" />
        <InsightHelpLabel
          label={t('Available soil water storage')}
          help={t('This is how much water the soil can store for plants. Current moisture varies.')}
        />
      </h3>
      <dl className="field-insights-water-comparison">
        <div>
          <dt>{t('Indexed field')}</dt>
          <dd>{formatMm(value)}</dd>
        </div>
        {median != null && (
          <div>
            <dt>{t('Regional median')}</dt>
            <dd>{formatMm(median)}</dd>
          </div>
        )}
      </dl>
      {median != null && <p className="field-insights-water-difference">{comparison}</p>}
    </div>
  );
}

type M3CropPanelProps = { crop: M3Crop; insights: M3Insights };

function M3CropPanel({ crop, insights }: M3CropPanelProps) {
  const { t } = useTranslation();
  const risk = insights.risk?.now[crop];
  const current = insights.windows?.now;
  const plantedError = insights.meta?.nass_validation_mae_days?.[crop]?.planted;
  const delays = insights.delay_scan?.now?.obs?.[crop];
  const water = insights.fallow_zero?.[crop === 'corn' ? 'after_soybeans' : 'after_corn'];

  return (
    <div className="field-insights-panel">
      <h3>
        <InsightHelpLabel
          label={t('Typical season')}
          help={
            <div className="field-insights-help-copy">
              <span>
                {t(
                  'Planting and risk estimates use weather for the area around the saved field. Dates describe typical seasons.',
                )}
              </span>
              {plantedError != null && (
                <span>
                  {t(
                    'In USDA validation, modeled sowing dates differed by about {{days}} days on average.',
                    {
                      days: Math.round(plantedError),
                    },
                  )}
                </span>
              )}
            </div>
          }
        />
      </h3>
      <M3DateTimeline
        entries={Object.entries(stages).map(([key, label]) => ({
          key,
          label,
          window: current?.[`${crop}:${key}`],
        }))}
        scaleWindows={Object.keys(crops).flatMap((cropKey) =>
          Object.keys(stages).map((stage) => current?.[`${cropKey}:${stage}`]),
        )}
      />
      {risk && <M3TypicalRisk risk={risk} delays={delays} />}
      <M3SowingDelay rows={delays} />
      <M3Outlook crop={crop} insights={insights} />
      <M3CoverCropWater water={water} />
    </div>
  );
}

const typicalHeatThreshold = 0.4;
const frostRiskLimit = 0.1;

type M3TypicalRiskProps = { risk: M3CurrentRisk; delays: M3Delay[] | undefined };

function M3TypicalRisk({ risk, delays }: M3TypicalRiskProps) {
  const { t, i18n } = useTranslation();
  const percent = (value: number) => insightNumber(value, i18n.language, 'percent');
  const days = (value: number) => insightNumber(value, i18n.language);
  const margin = risk.adaptation_margin_days;
  const scanDays = delays?.length ? Math.max(...delays.map(({ delay_days }) => delay_days)) : 30;
  const maxDelay = Math.max(scanDays, margin ?? 0);
  const delayWidth = maxDelay > 0 && margin != null ? (margin / maxDelay) * 100 : 0;
  let flexibility = t('The model did not identify a safe sowing delay.');
  if (margin === 0) {
    flexibility = t('No room to delay');
  } else if (margin != null) {
    flexibility = t('Up to {{days}} days of delay within modeled risk limits.', {
      days: days(margin),
    });
  }

  return (
    <section className="field-insights-panel">
      <h3>{t('Risk at typical sowing')}</h3>
      <M3TypicalRiskRow
        label={t('Heat during flowering')}
        value={risk.p_heat_overlap}
        threshold={typicalHeatThreshold}
        elevated={risk.p_heat_overlap != null && risk.p_heat_overlap >= typicalHeatThreshold}
        range={[risk.p_heat_lo80, risk.p_heat_hi80]}
        help={t('Share of years with at least two days at 35°C or higher during flowering.')}
        format={percent}
      />
      <M3TypicalRiskRow
        label={t('Frost before maturity')}
        value={risk.p_frost_before_maturity}
        threshold={frostRiskLimit}
        elevated={
          risk.p_frost_before_maturity != null && risk.p_frost_before_maturity > frostRiskLimit
        }
        help={
          risk.n_years != null && t('Based on {{count}} modeled years', { count: risk.n_years })
        }
        format={percent}
      />
      <div className="field-insights-season-stage">
        <div className="field-insights-outlook-label">
          <strong>{t('Planting flexibility')}</strong>
          <span
            className={margin == null ? undefined : 'field-insights-risk-value'}
            data-elevated={margin === 0}
          >
            {flexibility}
          </span>
          {risk.workable_days_q50 != null && (
            <small>
              {t('{{days}} workable days in a typical planting window', {
                days: days(risk.workable_days_q50),
              })}
            </small>
          )}
        </div>
        {margin != null && maxDelay > 0 && (
          <>
            <div className="field-insights-season-chart" aria-hidden="true">
              <div className="field-insights-season-track">
                <span className="field-insights-season-range" style={{ width: `${delayWidth}%` }} />
                <span
                  className="field-insights-season-marker field-insights-risk-value"
                  data-elevated={margin === 0}
                  style={{ left: `${delayWidth}%` }}
                />
              </div>
            </div>
            <div className="field-insights-season-axis" aria-hidden="true">
              <span>{days(0)}</span>
              <span>{t('{{days}} days of delay', { days: days(maxDelay) })}</span>
            </div>
          </>
        )}
      </div>
    </section>
  );
}

type M3TypicalRiskRowProps = {
  label: string;
  value: number | null;
  threshold: number;
  elevated: boolean;
  range?: [number | null, number | null];
  help: ReactNode;
  format: (value: number) => string;
};

function M3TypicalRiskRow({
  label,
  value,
  threshold,
  elevated,
  range = [null, null],
  help,
  format,
}: M3TypicalRiskRowProps) {
  const { t } = useTranslation();
  const [lower, upper] = range;
  const hasRange = lower != null && upper != null && upper >= lower;
  const position = (probability: number) => `${probability * 100}%`;

  return (
    <div className="field-insights-season-stage">
      <div className="field-insights-outlook-label">
        <strong>
          <InsightHelpLabel label={label} help={help} />
        </strong>
        {value == null ? (
          <span>{t('No data')}</span>
        ) : (
          <>
            <span className="field-insights-risk-value" data-elevated={elevated}>
              {t('{{value}} · {{level}}', {
                value: format(value),
                level: elevated ? t('Elevated risk') : t('Within model limit'),
              })}
            </span>
            {hasRange && (
              <small>
                {t('80% uncertainty interval: {{start}}–{{end}}', {
                  start: format(lower),
                  end: format(upper),
                })}
              </small>
            )}
            <small>{t('Model threshold · {{value}}', { value: format(threshold) })}</small>
          </>
        )}
      </div>
      {value != null && (
        <>
          <div className="field-insights-season-chart" aria-hidden="true">
            <div
              className="field-insights-season-track field-insights-risk-track"
              style={{ '--risk-threshold': position(threshold) } as CSSProperties}
            >
              {hasRange && (
                <span
                  className="field-insights-season-range field-insights-risk-range"
                  style={{ left: position(lower), width: position(upper - lower) }}
                />
              )}
              <span
                className="field-insights-season-marker field-insights-risk-value"
                data-elevated={elevated}
                style={{ left: position(value) }}
              />
            </div>
          </div>
          <div className="field-insights-season-axis" aria-hidden="true">
            <span>{format(0)}</span>
            <span>{format(1)}</span>
          </div>
        </>
      )}
    </div>
  );
}

type M3DateTimelineProps = {
  entries: { key: string; label: string; window: M3Window | undefined }[];
  scaleWindows?: (M3Window | undefined)[];
};

function M3DateTimeline({ entries, scaleWindows }: M3DateTimelineProps) {
  const { t, i18n } = useTranslation();
  const dates = (scaleWindows ?? entries.map(({ window }) => window))
    .flatMap((window) => [window?.date_q10, window?.date_q50, window?.date_q90])
    .filter((date): date is string => !!date && Number.isFinite(seasonTime(date)))
    .sort();
  const first = dates[0];
  const last = dates.at(-1);
  const start = seasonTime(first);
  const duration = seasonTime(last) - start;
  const position = (date: string | null | undefined) =>
    ((seasonTime(date) - start) / duration) * 100;

  return (
    <Timeline
      orientation="vertical"
      items={entries.map(({ key, label, window }, index) => {
        const median = position(window?.date_q50);
        const lower = position(window?.date_q10);
        const upper = position(window?.date_q90);
        const showRange = Number.isFinite(lower) && Number.isFinite(upper) && upper >= lower;

        return {
          key,
          content: (
            <div className="field-insights-season-stage">
              <strong>{t(label)}</strong>
              <div className="field-insights-season-dates">
                <WindowDates window={window} />
              </div>
              {duration > 0 && (index === 0 || Number.isFinite(median)) && (
                <div className="field-insights-season-chart" aria-hidden="true">
                  <div className="field-insights-season-track">
                    {showRange && Number.isFinite(median) && (
                      <span
                        className="field-insights-season-range"
                        style={{
                          left: `${lower}%`,
                          width: `${upper - lower}%`,
                        }}
                      />
                    )}
                    {Number.isFinite(median) && (
                      <span
                        className="field-insights-season-marker"
                        style={{ left: `${median}%` }}
                      />
                    )}
                  </div>
                  {index === 0 && (
                    <div className="field-insights-season-axis">
                      <span>{insightDate(first, i18n.language)}</span>
                      <span>{insightDate(last, i18n.language)}</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          ),
        };
      })}
    />
  );
}

function seasonTime(date: string | null | undefined) {
  return date ? Date.parse(`2001-${date}T00:00:00Z`) : NaN;
}

const delayRiskSeries = [
  { key: 'p_heat', label: 'Heat during flowering', color: '#a44730', dash: undefined },
  { key: 'p_frost', label: 'Frost before maturity', color: '#336d9c', dash: '6 4' },
] as const;

const delayRiskBands = [
  { from: 0, to: 0.25, label: 'Low likelihood', color: '#e7f0e1' },
  { from: 0.25, to: 0.5, label: 'Moderate likelihood', color: '#faf0d7' },
  { from: 0.5, to: 1, label: 'High likelihood', color: '#f7e0dc' },
] as const;

type M3SowingDelayProps = { rows: M3Delay[] | undefined };

function M3SowingDelay({ rows }: M3SowingDelayProps) {
  const { t, i18n } = useTranslation();
  if (!rows?.length) {
    return null;
  }
  const data = [...rows].sort((a, b) => a.delay_days - b.delay_days);
  const percent = (value: number) => insightNumber(value, i18n.language, 'percent');
  const days = (value: number) => insightNumber(value, i18n.language);

  return (
    <section className="field-insights-panel">
      <h3>{t('Risk by sowing delay')}</h3>
      {data.some(({ p_heat, p_frost }) => p_heat != null || p_frost != null) ? (
        <figure className="field-insights-sowing-chart">
          <ResponsiveContainer width="100%" height={260} minWidth={0}>
            <LineChart
              data={data}
              margin={{ top: 10, right: 16, bottom: 22, left: 0 }}
              title={t('Risk by sowing delay')}
              accessibilityLayer
            >
              {delayRiskBands.map(({ from, to, color }) => (
                <ReferenceArea
                  key={from}
                  y1={from}
                  y2={to}
                  fill={color}
                  fillOpacity={1}
                  zIndex={-110}
                />
              ))}
              <CartesianGrid vertical={false} stroke="#e2e7df" />
              <XAxis
                dataKey="delay_days"
                type="number"
                domain={['dataMin', 'dataMax']}
                ticks={data.map(({ delay_days }) => delay_days)}
                tickFormatter={days}
                tickLine={false}
                tick={{ fill: '#52624a', fontSize: 12 }}
                label={{
                  value: t('Sowing delay (days)'),
                  position: 'insideBottom',
                  offset: -12,
                  fill: '#52624a',
                  fontSize: 12,
                }}
              />
              <YAxis
                domain={[0, 1]}
                ticks={[0, 0.25, 0.5, 0.75, 1]}
                tickFormatter={percent}
                width={48}
                axisLine={false}
                tickLine={false}
                tick={{ fill: '#52624a', fontSize: 12 }}
              />
              <ChartTooltip
                labelFormatter={(value) =>
                  t('Sowing delay (days) · {{value}}', { value: days(Number(value)) })
                }
                formatter={(value) => {
                  if (typeof value !== 'number') {
                    return t('No data');
                  }
                  const band = delayRiskBands.findLast(({ from }) => value >= from);
                  return band
                    ? t('{{value}} · {{level}}', { value: percent(value), level: t(band.label) })
                    : percent(value);
                }}
                filterNull={false}
              />
              {delayRiskSeries.map(({ key, label, color, dash }) => (
                <Line
                  key={key}
                  name={t(label)}
                  dataKey={key}
                  stroke={color}
                  strokeDasharray={dash}
                  strokeWidth={2.5}
                  dot={{ r: 3, fill: '#fff' }}
                  activeDot={{ r: 5 }}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
          <figcaption className="field-insights-sowing-legend">
            {delayRiskSeries.map(({ key, label, color, dash }) => (
              <span key={key}>
                <i
                  className="field-insights-sowing-line"
                  aria-hidden="true"
                  style={{ borderColor: color, borderTopStyle: dash ? 'dashed' : 'solid' }}
                />
                {t(label)}
              </span>
            ))}
          </figcaption>
        </figure>
      ) : (
        <p>{t('No data')}</p>
      )}
    </section>
  );
}

type WindowDatesProps = { window: M3Window | undefined };

function WindowDates({ window }: WindowDatesProps) {
  const { t, i18n } = useTranslation();
  const date = (value: string | null | undefined) => insightDate(value, i18n.language);
  const limited =
    window &&
    (window.calibrated === false ||
      (window.n_years_fit ?? Infinity) < 15 ||
      (window.censored_share ?? 0) > 0.2);

  if (!window?.date_q50) {
    return <span>{t('No data')}</span>;
  }

  return (
    <>
      <span>{t('Around {{date}}', { date: date(window.date_q50) })}</span>
      {window.date_q10 && window.date_q90 && (
        <small>
          {t('Usually {{start}}–{{end}}', {
            start: date(window.date_q10),
            end: date(window.date_q90),
          })}
        </small>
      )}
      {limited && <small>{t('Limited model evidence')}</small>}
    </>
  );
}

type ScenarioRange = {
  scenario: M3Scenario;
  estimate: number;
  lower: number;
  upper: number;
};

const dayMs = 24 * 60 * 60 * 1000;

function M3Outlook({ crop, insights }: M3CropPanelProps) {
  const { t, i18n } = useTranslation();
  const scenarioIds = Object.keys(scenarios) as M3Scenario[];
  const dates = (value: number) =>
    insightDate(new Date(value).toISOString().slice(5, 10), i18n.language);
  const percent = (value: number) => insightNumber(value, i18n.language, 'percent');
  const stageEntries = Object.entries(stages).flatMap(([key, label]) => {
    const ranges = scenarioIds.flatMap((scenario) => {
      const window = insights.windows?.future[scenario]?.[`${crop}:${key}`];
      const estimate = seasonTime(window?.date_q50_median);
      if (!Number.isFinite(estimate)) {
        return [];
      }
      return [
        {
          scenario,
          estimate,
          lower: seasonTime(window?.date_q50_min),
          upper: seasonTime(window?.date_q50_max),
        },
      ];
    });
    return ranges.length > 0 ? [{ key, label, ranges }] : [];
  });
  const heat = scenarioIds.flatMap((scenario) => {
    const risk = insights.risk?.future[scenario]?.[crop];
    if (risk?.p_heat_median == null) {
      return [];
    }
    return [
      {
        scenario,
        estimate: risk.p_heat_median,
        lower: risk.p_heat_min ?? NaN,
        upper: risk.p_heat_max ?? NaN,
      },
    ];
  });
  if (stageEntries.length === 0 && heat.length === 0) {
    return null;
  }

  return (
    <section className="field-insights-panel">
      <h3>
        <InsightHelpLabel
          label={t('2040 climate outlook')}
          help={t('Ranges show how climate models differ under each emissions scenario.')}
        />
      </h3>
      <div className="field-insights-outlook">
        {stageEntries.length > 0 && (
          <Timeline
            orientation="vertical"
            items={stageEntries.map(({ key, label, ranges }) => {
              const values = ranges
                .flatMap(({ estimate, lower, upper }) => [estimate, lower, upper])
                .filter(Number.isFinite);

              return {
                key,
                content: (
                  <div className="field-insights-season-stage">
                    <strong>{t(label)}</strong>
                    <M3RangeComparison
                      ranges={ranges}
                      min={Math.min(...values) - dayMs}
                      max={Math.max(...values) + dayMs}
                      format={dates}
                    />
                  </div>
                ),
              };
            })}
          />
        )}
        {heat.length > 0 && (
          <div className="field-insights-season-stage">
            <strong>
              <InsightHelpLabel
                label={t('Heat during flowering')}
                help={t(
                  'Share of years with at least two days at 35°C or higher during flowering.',
                )}
              />
            </strong>
            <M3RangeComparison ranges={heat} min={0} max={1} format={percent} />
          </div>
        )}
      </div>
    </section>
  );
}

type M3RangeComparisonProps = {
  ranges: ScenarioRange[];
  min: number;
  max: number;
  format: (value: number) => string;
};

function M3RangeComparison({ ranges, min, max, format }: M3RangeComparisonProps) {
  const { t } = useTranslation();
  const position = (value: number) => ((value - min) / (max - min)) * 100;

  return (
    <div className="field-insights-outlook-comparison">
      {ranges.map(({ scenario, estimate, lower, upper }) => {
        const colors = scenarioColors[scenario];
        const hasRange = Number.isFinite(lower) && Number.isFinite(upper) && upper >= lower;

        return (
          <div key={scenario}>
            <div className="field-insights-outlook-label">
              <strong style={{ color: colors.marker }}>{t(scenarios[scenario])}</strong>
              <span>{format(estimate)}</span>
              {hasRange && (
                <small>
                  {t('Predicted range: {{start}}–{{end}}', {
                    start: format(lower),
                    end: format(upper),
                  })}
                </small>
              )}
            </div>
            <div className="field-insights-season-chart" aria-hidden="true">
              <div className="field-insights-season-track">
                {hasRange && (
                  <span
                    className="field-insights-season-range"
                    style={{
                      left: `${position(lower)}%`,
                      width: `${position(upper) - position(lower)}%`,
                      background: colors.range,
                    }}
                  />
                )}
                <span
                  className="field-insights-season-marker"
                  style={{ left: `${position(estimate)}%`, background: colors.marker }}
                />
              </div>
            </div>
          </div>
        );
      })}
      <div className="field-insights-season-axis" aria-hidden="true">
        <span>{format(min)}</span>
        <span>{format(max)}</span>
      </div>
    </div>
  );
}

type M3CoverCropWaterProps = { water: M3Water | undefined };

function M3CoverCropWater({ water }: M3CoverCropWaterProps) {
  const { t, i18n } = useTranslation();
  if (!water?.bare && !water?.cover) {
    return null;
  }

  return (
    <section className="field-insights-panel">
      <h3>{t('Cover crop and water at sowing')}</h3>
      <div className="field-insights-grid">
        {(
          [
            [water.bare, 'Bare fallow'],
            [water.cover, 'Winter rye cover'],
          ] as const
        ).map(
          ([branch, label]) =>
            branch && (
              <Card key={label} size="small" title={t(label)} className="field-insights-metric">
                {branch.paw_sow_mm.q50 != null && (
                  <span>
                    {t('{{value}} mm of plant-available water at typical sowing', {
                      value: insightNumber(branch.paw_sow_mm.q50, i18n.language),
                    })}
                  </span>
                )}
                {branch.p_shortfall != null && (
                  <span>
                    {t('Water shortfall in {{value}} of modeled years', {
                      value: insightNumber(branch.p_shortfall, i18n.language, 'percent'),
                    })}
                  </span>
                )}
                {branch.safe_autumn_rain_mm != null && (
                  <span>
                    {t('Modeled autumn rain threshold of {{value}} mm', {
                      value: insightNumber(branch.safe_autumn_rain_mm, i18n.language),
                    })}
                  </span>
                )}
              </Card>
            ),
        )}
      </div>
    </section>
  );
}
