import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Card, Empty, Skeleton, Tabs, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { fieldInsightsQueries } from '../../../api/fields/field-insights.queries.ts';
import type {
  M3Crop,
  M3Delay,
  M3FutureRisk,
  M3FutureWindow,
  M3Insights,
  M3Scenario,
  M3Water,
  M3Window,
} from '../../../types/fields/field-insights.types.ts';
import type { Field } from '../../../types/fields/field.types.ts';
import { insightDate, insightNumber } from '../utils/fieldInsightFormats.ts';
import './FieldInsights.css';

const crops = { corn: 'Corn', soybeans: 'Soybeans' } as const;
const scenarios = { ssp245: 'Intermediate emissions', ssp585: 'High emissions' } as const;
const stages = {
  first_ready: 'First workable planting day',
  sow: 'Sowing',
  flower: 'Flowering',
  mature: 'Maturity',
} as const;

type FieldM3InsightsProps = { field: Field };

export function FieldM3Insights({ field }: FieldM3InsightsProps) {
  const { t } = useTranslation();
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

  return <Card title={t('Crop timing and climate risk')}>{content}</Card>;
}

type M3ResultsProps = { insights: M3Insights };

function M3Results({ insights }: M3ResultsProps) {
  const { t, i18n } = useTranslation();
  const match = insights.match;
  const matchText = match?.level === 'field' ? t('Nearby indexed field') : t('Weather cell only');
  const current = insights.windows?.now;
  const frosts = [
    { key: 'last_spring_frost', label: 'Last spring frost' },
    { key: 'first_autumn_frost', label: 'First autumn frost' },
  ] as const;

  return (
    <div className="field-insights-panel">
      <div className="field-insights-heading">
        <Tag color={match?.level === 'field' ? 'green' : 'blue'}>{matchText}</Tag>
        {match && (
          <span>
            {match.level === 'field'
              ? t('Indexed field center {{distance}} km away', {
                  distance: insightNumber(match.distance_km, i18n.language),
                })
              : t('Weather cell center {{distance}} km away', {
                  distance: insightNumber(match.distance_km, i18n.language),
                })}
          </span>
        )}
        {match?.awc_mm != null && (
          <span>
            {t('{{value}} mm of available soil water storage at the indexed field', {
              value: insightNumber(match.awc_mm, i18n.language),
            })}
          </span>
        )}
      </div>
      <Typography.Text type="secondary">
        {t(
          'Planting and risk estimates use weather for the area around the saved field. Dates describe typical seasons.',
        )}
      </Typography.Text>
      <div className="field-insights-grid">
        {frosts
          .filter(({ key }) => current?.[key]?.date_q50)
          .map(({ key, label }) => (
            <Card key={key} size="small" className="field-insights-metric">
              <strong>{t(label)}</strong>
              <WindowDates window={current?.[key]} />
            </Card>
          ))}
      </div>
      <Tabs
        items={(Object.keys(crops) as M3Crop[]).map((crop) => ({
          key: crop,
          label: t(crops[crop]),
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
      <small>
        {t('Source')} · {t('M3 crop timing model')}
      </small>
    </div>
  );
}

type M3CropPanelProps = { crop: M3Crop; insights: M3Insights };

function M3CropPanel({ crop, insights }: M3CropPanelProps) {
  const { t, i18n } = useTranslation();
  const risk = insights.risk?.now[crop];
  const current = insights.windows?.now;
  const plantedError = insights.meta?.nass_validation_mae_days?.[crop]?.planted;
  const percent = (value: number | null) => insightNumber(value, i18n.language, 'percent');
  const water = insights.fallow_zero?.[crop === 'corn' ? 'after_soybeans' : 'after_corn'];

  return (
    <div className="field-insights-panel">
      <h3>{t('Typical season')}</h3>
      <div className="field-insights-grid field-insights-season">
        {Object.entries(stages).map(([key, label]) => (
          <Card key={key} size="small" className="field-insights-metric">
            <strong>{t(label)}</strong>
            <WindowDates window={current?.[`${crop}:${key}`]} />
          </Card>
        ))}
      </div>
      {plantedError != null && (
        <Typography.Text type="secondary">
          {t(
            'In USDA validation, modeled sowing dates differed by about {{days}} days on average.',
            {
              days: Math.round(plantedError),
            },
          )}
        </Typography.Text>
      )}
      {risk && (
        <>
          <h3>{t('Risk at typical sowing')}</h3>
          <div className="field-insights-grid">
            <Card size="small" className="field-insights-metric">
              <strong>{t('Heat during flowering')}</strong>
              <span>{percent(risk.p_heat_overlap)}</span>
              <small>
                {t('Share of years with at least two days at 35°C or higher during flowering.')}
              </small>
              {risk.p_heat_lo80 != null && risk.p_heat_hi80 != null && (
                <small>
                  {t('80% uncertainty interval: {{start}}–{{end}}', {
                    start: percent(risk.p_heat_lo80),
                    end: percent(risk.p_heat_hi80),
                  })}
                </small>
              )}
            </Card>
            <Card size="small" className="field-insights-metric">
              <strong>{t('Frost before maturity')}</strong>
              <span>{percent(risk.p_frost_before_maturity)}</span>
              {risk.n_years != null && (
                <small>{t('Based on {{count}} modeled years', { count: risk.n_years })}</small>
              )}
            </Card>
            <Card size="small" className="field-insights-metric">
              <strong>{t('Planting flexibility')}</strong>
              {risk.workable_days_q50 != null && (
                <span>
                  {t('{{days}} workable days in a typical planting window', {
                    days: insightNumber(risk.workable_days_q50, i18n.language),
                  })}
                </span>
              )}
              <small>
                {risk.adaptation_margin_days == null
                  ? t('The model did not identify a safe sowing delay.')
                  : t('Up to {{days}} days of delay within modeled risk limits.', {
                      days: risk.adaptation_margin_days,
                    })}
              </small>
            </Card>
          </div>
        </>
      )}
      <M3SowingDelay rows={insights.delay_scan?.now?.obs?.[crop]} />
      <M3Outlook crop={crop} insights={insights} />
      {water ? (
        <M3CoverCropWater water={water} />
      ) : (
        <Typography.Text type="secondary">
          {t('Cover-crop water estimates are unavailable for this location.')}
        </Typography.Text>
      )}
    </div>
  );
}

type M3SowingDelayProps = { rows: M3Delay[] | undefined };

function M3SowingDelay({ rows }: M3SowingDelayProps) {
  const { t, i18n } = useTranslation();
  if (!rows?.length) {
    return null;
  }

  return (
    <details>
      <summary>{t('Risk by sowing delay')}</summary>
      <table className="field-insights-table">
        <thead>
          <tr>
            <th scope="col">{t('Sowing delay (days)')}</th>
            <th scope="col">{t('Heat during flowering')}</th>
            <th scope="col">{t('Frost before maturity')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.delay_days}>
              <th scope="row">{insightNumber(row.delay_days, i18n.language)}</th>
              <td>{insightNumber(row.p_heat, i18n.language, 'percent')}</td>
              <td>{insightNumber(row.p_frost, i18n.language, 'percent')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
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

function M3Outlook({ crop, insights }: M3CropPanelProps) {
  const { t } = useTranslation();
  const outlook = (Object.keys(scenarios) as M3Scenario[]).flatMap((scenario) => {
    const windows = insights.windows?.future[scenario];
    const risk = insights.risk?.future[scenario]?.[crop];
    return windows || risk ? [{ scenario, windows, risk }] : [];
  });
  if (outlook.length === 0) {
    return null;
  }

  return (
    <details>
      <summary>{t('2040 climate outlook')}</summary>
      <p>{t('Ranges show how climate models differ under each emissions scenario.')}</p>
      <div className="field-insights-grid">
        {outlook.map(({ scenario, windows, risk }) => (
          <M3ScenarioCard
            key={scenario}
            scenario={scenario}
            crop={crop}
            windows={windows}
            risk={risk}
          />
        ))}
      </div>
    </details>
  );
}

type M3ScenarioCardProps = {
  scenario: M3Scenario;
  crop: M3Crop;
  windows: Record<string, M3FutureWindow> | undefined;
  risk: M3FutureRisk | undefined;
};

function M3ScenarioCard({ scenario, crop, windows, risk }: M3ScenarioCardProps) {
  const { t, i18n } = useTranslation();
  const percent = (value: number | null) => insightNumber(value, i18n.language, 'percent');
  const models = risk?.n_models ?? windows?.[`${crop}:mature`]?.n_models;

  return (
    <Card size="small" title={t(scenarios[scenario])} className="field-insights-metric">
      {Object.entries(stages).map(([stage, label]) => {
        const window = windows?.[`${crop}:${stage}`];
        if (!window?.date_q50_median) {
          return null;
        }

        return (
          <div key={stage}>
            <strong>{t(label)}</strong>
            <div>
              {t('Around {{date}}', { date: insightDate(window.date_q50_median, i18n.language) })}
            </div>
            {window.date_q50_min && window.date_q50_max && (
              <small>
                {t('Model range: {{start}}–{{end}}', {
                  start: insightDate(window.date_q50_min, i18n.language),
                  end: insightDate(window.date_q50_max, i18n.language),
                })}
              </small>
            )}
          </div>
        );
      })}
      {risk?.p_heat_median != null && (
        <div>
          <strong>{t('Heat during flowering')}</strong>
          <div>{percent(risk.p_heat_median)}</div>
          {risk.p_heat_min != null && risk.p_heat_max != null && (
            <small>
              {t('Model range: {{start}}–{{end}}', {
                start: percent(risk.p_heat_min),
                end: percent(risk.p_heat_max),
              })}
            </small>
          )}
        </div>
      )}
      {risk?.margin_min != null && risk.margin_max != null && (
        <span>
          {t('Modeled sowing delay of {{start}}–{{end}} days', {
            start: risk.margin_min,
            end: risk.margin_max,
          })}
        </span>
      )}
      {models != null && <small>{t('Based on {{count}} climate models', { count: models })}</small>}
    </Card>
  );
}

type M3CoverCropWaterProps = { water: M3Water | undefined };

function M3CoverCropWater({ water }: M3CoverCropWaterProps) {
  const { t, i18n } = useTranslation();
  if (!water?.bare && !water?.cover) {
    return null;
  }

  return (
    <details>
      <summary>{t('Cover crop and water at sowing')}</summary>
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
    </details>
  );
}
