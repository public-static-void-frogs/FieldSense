import { Collapse, Table, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import type {
  RotationAdvice,
  RotationPlan,
  RotationPlanCrop,
  RotationPlanStep,
  RotationSimulatedOutcome,
} from '../../../types/rotation/rotation.types.ts';
import { autumnActionLabels, tillageLabels, yieldModeLabels } from '../constants/rotationLabels.ts';
import { cropNamer, formatSignedUsd, rankedPlanCrops } from '../utils/planPresentation.ts';
import { formatNumber, formatPercent } from '../utils/rotationPresentation.ts';
import { OutcomeChart } from './OutcomeChart';

type PlanForecastProps = { advice: RotationAdvice; plan: RotationPlan; entry: RotationPlanCrop };

export function PlanForecast({ advice, plan, entry }: PlanForecastProps) {
  const { t, i18n } = useTranslation();
  const language = i18n.language;
  const name = cropNamer(advice);
  const { firstSeason, plan: wholePlan } = entry.simulation;
  const yields = firstSeason.yieldPerAcre;
  const year = plan.firstSeason;
  const top = rankedPlanCrops(plan)[0];
  const usd = (value: number) => formatSignedUsd(value, language);
  const chartLabel = t('Result per acre in {{year}} under each past year', { year });

  return (
    <section className="rotation-forecast">
      <Typography.Title level={5}>{t('Forecast for {{year}}', { year })}</Typography.Title>
      <dl className="rotation-stats rotation-stats-wide">
        <div>
          <dt>{t('Chance of a loss')}</dt>
          <dd>{formatPercent(firstSeason.lossProbability, language)}</dd>
        </div>
        <div>
          <dt>{t('Typical result per acre')}</dt>
          <dd>{usd(firstSeason.p50UsdPerAcre)}</dd>
        </div>
        <div>
          <dt>{t('Poor year to good year')}</dt>
          <dd>
            {t('{{low}} to {{high}}', {
              low: usd(firstSeason.p10UsdPerAcre),
              high: usd(firstSeason.p90UsdPerAcre),
            })}
          </dd>
        </div>
        <div>
          <dt>{t('Expected yield, {{unit}}', { unit: yields.unit })}</dt>
          <dd>
            {formatNumber(yields.meanPerAcre, language)}{' '}
            <small>
              {t('{{low}} to {{high}}', {
                low: formatNumber(yields.p10PerAcre, language),
                high: formatNumber(yields.p90PerAcre, language),
              })}
            </small>
          </dd>
        </div>
        <div>
          <dt>{t('Planning price, USD per {{unit}}', { unit: yields.unit.split('/')[0] })}</dt>
          <dd>{formatNumber(firstSeason.planningPriceUsd, language, 2)}</dd>
        </div>
        <div>
          <dt>{t('Worst year on record')}</dt>
          <dd>
            {usd(firstSeason.worst.netUsdPerAcre)} <small>{firstSeason.worst.year}</small>
          </dd>
        </div>
        <div>
          <dt>{t('Best year on record')}</dt>
          <dd>
            {usd(firstSeason.best.netUsdPerAcre)} <small>{firstSeason.best.year}</small>
          </dd>
        </div>
        {firstSeason.beatsTopProbability !== null && top && top.crop !== entry.crop && (
          <div>
            <dt>{t('Earns at least as much as {{crop}}', { crop: t(name(top.crop)) })}</dt>
            <dd>
              {t('{{share}} of years', {
                share: formatPercent(firstSeason.beatsTopProbability, language),
              })}
            </dd>
          </div>
        )}
      </dl>
      <Typography.Title level={5}>{chartLabel}</Typography.Title>
      <OutcomeChart outcomes={firstSeason.outcomes} yieldUnit={yields.unit} label={chartLabel} />
      <Typography.Paragraph type="secondary">
        {t(
          'Yields in {{observed}} of {{years}} years are county or state records; the others are modelled from that year’s weather. "Poor" and "good" mean one year in ten is worse or better.',
          { observed: firstSeason.observedYieldYears, years: firstSeason.years },
        )}
      </Typography.Paragraph>
      <Collapse
        ghost
        size="small"
        items={[
          {
            key: 'years',
            label: t('Show the years as a table'),
            children: <OutcomeTable outcomes={firstSeason.outcomes} yieldUnit={yields.unit} />,
          },
        ]}
      />
      <Typography.Title level={5}>{t('Season by season')}</Typography.Title>
      <StepTable advice={advice} steps={entry.steps} />
      {wholePlan && plan.seasons > 1 && (
        <>
          <Typography.Title level={5}>
            {t('All {{seasons}} seasons together', { seasons: plan.seasons })}
          </Typography.Title>
          <dl className="rotation-stats rotation-stats-wide">
            <div>
              <dt>{t('Chance of a loss')}</dt>
              <dd>{formatPercent(wholePlan.lossProbability, language)}</dd>
            </div>
            <div>
              <dt>{t('Typical result per acre')}</dt>
              <dd>{usd(wholePlan.p50UsdPerAcre)}</dd>
            </div>
            <div>
              <dt>{t('Poor run to good run')}</dt>
              <dd>
                {t('{{low}} to {{high}}', {
                  low: usd(wholePlan.p10UsdPerAcre),
                  high: usd(wholePlan.p90UsdPerAcre),
                })}
              </dd>
            </div>
            <div>
              <dt>{t('Worst start year')}</dt>
              <dd>
                {usd(wholePlan.worst.netUsdPerAcre)} <small>{wholePlan.worst.year}</small>
              </dd>
            </div>
            <div>
              <dt>{t('Best start year')}</dt>
              <dd>
                {usd(wholePlan.best.netUsdPerAcre)} <small>{wholePlan.best.year}</small>
              </dd>
            </div>
          </dl>
          <Typography.Paragraph type="secondary">
            {t(
              'The whole plan was started in each of {{runs}} past years and run through the years that really followed.',
              { runs: wholePlan.runs },
            )}
          </Typography.Paragraph>
        </>
      )}
    </section>
  );
}

type StepTableProps = { advice: RotationAdvice; steps: RotationPlanStep[] };

function StepTable({ advice, steps }: StepTableProps) {
  const { t, i18n } = useTranslation();
  const language = i18n.language;
  const name = cropNamer(advice);
  const usd = (value: number) => formatSignedUsd(value, language);

  return (
    <Table<RotationPlanStep>
      className="rotation-table"
      size="small"
      rowKey="season"
      pagination={false}
      scroll={{ x: 'max-content' }}
      dataSource={steps}
      columns={[
        { title: t('Season'), dataIndex: 'season' },
        { title: t('Crop'), render: (_, step) => t(name(step.crop)) },
        {
          title: t('Autumn before'),
          render: (_, step) => t(autumnActionLabels[step.autumnBefore] ?? step.autumnBefore),
        },
        {
          title: t('Tillage'),
          render: (_, step) => t(tillageLabels[step.tillage] ?? step.tillage),
        },
        {
          title: t('Yield'),
          align: 'right',
          render: (_, step) => `${formatNumber(step.yieldPerAcre, language)} ${step.yieldUnit}`,
        },
        { title: t('Sales'), align: 'right', render: (_, step) => usd(step.revenueUsdPerAcre) },
        { title: t('Cost'), align: 'right', render: (_, step) => usd(step.costUsdPerAcre) },
        {
          title: t('Average result'),
          align: 'right',
          render: (_, step) => usd(step.netUsdPerAcre),
        },
        {
          title: t('Worst year'),
          align: 'right',
          render: (_, step) => `${usd(step.worstYearUsdPerAcre)} (${step.worstYear})`,
        },
      ]}
    />
  );
}

type OutcomeTableProps = { outcomes: RotationSimulatedOutcome[]; yieldUnit: string };

function OutcomeTable({ outcomes, yieldUnit }: OutcomeTableProps) {
  const { t, i18n } = useTranslation();
  const language = i18n.language;

  return (
    <Table<RotationSimulatedOutcome>
      className="rotation-table"
      size="small"
      rowKey="year"
      pagination={false}
      scroll={{ x: 'max-content', y: 320 }}
      dataSource={[...outcomes].sort((left, right) => right.year - left.year)}
      columns={[
        { title: t('Year'), dataIndex: 'year' },
        {
          title: t('Result'),
          align: 'right',
          render: (_, row) => formatSignedUsd(row.netUsdPerAcre, language),
        },
        {
          title: `${t('Yield')}, ${yieldUnit}`,
          align: 'right',
          render: (_, row) => formatNumber(row.yieldPerAcre, language),
        },
        {
          title: t('Price'),
          align: 'right',
          render: (_, row) => formatNumber(row.priceUsd, language, 2),
        },
        {
          title: t('Weight'),
          align: 'right',
          render: (_, row) => formatPercent(row.probability, language),
        },
        {
          title: t('Yield source'),
          render: (_, row) => t(yieldModeLabels[row.yieldMode] ?? row.yieldMode),
        },
      ]}
    />
  );
}
