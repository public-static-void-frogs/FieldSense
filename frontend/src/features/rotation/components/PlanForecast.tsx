import { Flex, Segmented, Table, Typography } from 'antd';
import { ArrowDown, ArrowUp, Equal } from 'lucide-react';
import { useState, type ReactNode } from 'react';
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
  const [view, setView] = useState<'chart' | 'data'>('chart');
  const language = i18n.language;
  const name = cropNamer(advice);
  const { firstSeason, plan: wholePlan } = entry.simulation;
  const yields = firstSeason.yieldPerAcre;
  const year = plan.firstSeason;
  const top = rankedPlanCrops(plan)[0];
  const usd = (value: number) => formatSignedUsd(value, language);
  const yieldValue = (value: number) => formatNumber(value, language);
  const priceValue = (value: number) => formatNumber(value, language, 2);
  const chartLabel = t('Result per acre in {{year}} under each past year', { year });
  const previousYear = firstSeason.outcomes.find((outcome) => outcome.year + 1 === year);
  const previousYield = previousYear?.yieldMode === 'none' ? undefined : previousYear?.yieldPerAcre;
  const compare = (
    current: number,
    previous: number | undefined,
    format: (value: number) => string,
  ) => {
    if (!previousYear || previous === undefined) {
      return undefined;
    }

    const previousValue = format(previous);

    return {
      direction: format(current) === previousValue ? 0 : Math.sign(current - previous),
      label: t('vs {{value}} in the {{year}} replay', {
        value: previousValue,
        year: previousYear.year,
      }),
    };
  };

  return (
    <section className="rotation-forecast">
      <Flex
        className="rotation-forecast-toolbar"
        align="center"
        justify="space-between"
        gap={8}
        wrap
      >
        <Typography.Title level={5}>{chartLabel}</Typography.Title>
        <Segmented<'chart' | 'data'>
          size="small"
          aria-label={t('View for {{label}}', { label: chartLabel })}
          value={view}
          onChange={setView}
          options={[
            { label: t('Chart'), value: 'chart' },
            { label: t('Data'), value: 'data' },
          ]}
        />
      </Flex>
      {view === 'chart' ? (
        <OutcomeChart outcomes={firstSeason.outcomes} yieldUnit={yields.unit} label={chartLabel} />
      ) : (
        <OutcomeTable outcomes={firstSeason.outcomes} yieldUnit={yields.unit} />
      )}
      <Typography.Title level={5}>{t('Forecast for {{year}}', { year })}</Typography.Title>
      <dl className="rotation-forecast-metrics">
        <ForecastMetric label={t('Chance of a loss')}>
          {formatPercent(firstSeason.lossProbability, language)}
        </ForecastMetric>
        <ForecastMetric
          label={t('Typical result per acre')}
          comparison={compare(firstSeason.p50UsdPerAcre, previousYear?.netUsdPerAcre, usd)}
        >
          {usd(firstSeason.p50UsdPerAcre)}
        </ForecastMetric>
        <ForecastMetric label={t('Poor year to good year')}>
          {t('{{low}} to {{high}}', {
            low: usd(firstSeason.p10UsdPerAcre),
            high: usd(firstSeason.p90UsdPerAcre),
          })}
        </ForecastMetric>
        <ForecastMetric
          label={t('Expected yield, {{unit}}', { unit: yields.unit })}
          comparison={compare(yields.meanPerAcre, previousYield, yieldValue)}
        >
          {yieldValue(yields.meanPerAcre)}{' '}
          <small>
            {t('{{low}} to {{high}}', {
              low: yieldValue(yields.p10PerAcre),
              high: yieldValue(yields.p90PerAcre),
            })}
          </small>
        </ForecastMetric>
        <ForecastMetric
          label={t('Planning price, USD per {{unit}}', { unit: yields.unit.split('/')[0] })}
          comparison={compare(firstSeason.planningPriceUsd, previousYear?.priceUsd, priceValue)}
        >
          {priceValue(firstSeason.planningPriceUsd)}
        </ForecastMetric>
        <ForecastMetric label={t('Worst year on record')}>
          {usd(firstSeason.worst.netUsdPerAcre)} <small>{firstSeason.worst.year}</small>
        </ForecastMetric>
        <ForecastMetric label={t('Best year on record')}>
          {usd(firstSeason.best.netUsdPerAcre)} <small>{firstSeason.best.year}</small>
        </ForecastMetric>
        {firstSeason.beatsTopProbability !== null && top && top.crop !== entry.crop && (
          <ForecastMetric
            label={t('Earns at least as much as {{crop}}', { crop: t(name(top.crop)) })}
          >
            {t('{{share}} of years', {
              share: formatPercent(firstSeason.beatsTopProbability, language),
            })}
          </ForecastMetric>
        )}
      </dl>
      <Typography.Paragraph type="secondary">
        {t(
          'Yields in {{observed}} of {{years}} years are county or state records; the others are modelled from that year’s weather. "Poor" and "good" mean one year in ten is worse or better.',
          { observed: firstSeason.observedYieldYears, years: firstSeason.years },
        )}
      </Typography.Paragraph>
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

type ForecastMetricProps = {
  label: string;
  children: ReactNode;
  comparison?: { direction: number; label: string };
};

function ForecastMetric({ label, children, comparison }: ForecastMetricProps) {
  const { t } = useTranslation();
  let Icon = Equal;
  let direction = 'neutral';
  let meaning = comparison ? t('Same value') : t('No year-over-year comparison');
  if (comparison && comparison.direction > 0) {
    Icon = ArrowUp;
    direction = 'up';
    meaning = t('Higher');
  } else if (comparison && comparison.direction < 0) {
    Icon = ArrowDown;
    direction = 'down';
    meaning = t('Lower');
  }

  return (
    <div>
      <dt>{label}:</dt>
      <dd>
        <span>{children}</span>
        <span className="rotation-forecast-comparison">
          <span className="rotation-forecast-indicator" data-direction={direction}>
            <Icon size={17} strokeWidth={2.75} role="img" aria-label={meaning} />
          </span>
          {comparison && <small>{comparison.label}</small>}
        </span>
      </dd>
    </div>
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
