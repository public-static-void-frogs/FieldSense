import { Card, Flex, Tag, Typography } from 'antd';
import { ArrowRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useLocation } from 'react-router-dom';
import { CropIcon } from '../../../components/common/CropIcon';
import { RouterButton } from '../../../components/common/RouterButton';
import type {
  RotationAdvice,
  RotationCandidate,
  RotationPlan,
  RotationPlanCrop,
} from '../../../types/rotation/rotation.types.ts';
import {
  autumnActionLabels,
  establishmentColors,
  establishmentLabels,
  levelColors,
  levelLabels,
  notModelledLabels,
  planGapLabels,
} from '../constants/rotationLabels.ts';
import {
  cropNamer,
  formatSignedUsd,
  lastSeason,
  rankedPlanCrops,
  unpricedCandidates,
} from '../utils/planPresentation.ts';
import {
  distinctGapCodes,
  formatNumber,
  formatPercent,
  highestRiskLevel,
} from '../utils/rotationPresentation.ts';
import { recommendationPath } from '../utils/rotationRoutes.ts';

type PlanOverviewProps = { advice: RotationAdvice; plan: RotationPlan };

export function PlanOverview({ advice, plan }: PlanOverviewProps) {
  const { t } = useTranslation();
  const crops = rankedPlanCrops(plan);
  const top = crops.filter(({ tier }) => tier === 'top');
  const others = crops.filter(({ tier }) => tier !== 'top');
  const unpriced = unpricedCandidates(advice, plan);
  const candidates = new Map(advice.candidates.map((candidate) => [candidate.crop, candidate]));
  const first = plan.firstSeason;
  const last = lastSeason(plan);
  const title =
    first !== null && last !== null && last > first
      ? t('Plan for {{first}}–{{last}}', { first, last })
      : t('Plan for {{first}}', { first });

  return (
    <Card className="rotation-plan" title={title}>
      <Typography.Paragraph type="secondary">
        {t(
          'Each option is the best plan that starts with that crop. Money is per acre: sales less production cost, land rent not included.',
        )}
      </Typography.Paragraph>
      <ol className="rotation-plan-top">
        {top.map((entry) => (
          <PlanCard
            key={entry.crop}
            advice={advice}
            plan={plan}
            entry={entry}
            candidate={candidates.get(entry.crop)}
          />
        ))}
      </ol>
      {others.length > 0 && (
        <section className="rotation-plan-section">
          <Typography.Title level={5}>{t('Other options')}</Typography.Title>
          <ul className="rotation-candidates">
            {others.map((entry) => (
              <PlanRow
                key={entry.crop}
                advice={advice}
                plan={plan}
                entry={entry}
                candidate={candidates.get(entry.crop)}
              />
            ))}
          </ul>
        </section>
      )}
      {unpriced.length > 0 && (
        <section className="rotation-plan-section">
          <Typography.Title level={5}>{t('Not priced, rotation risk only')}</Typography.Title>
          <ul className="rotation-candidates">
            {unpriced.map((candidate) => (
              <UnpricedRow key={candidate.crop} advice={advice} candidate={candidate} />
            ))}
          </ul>
        </section>
      )}
      <PlanBasis plan={plan} />
    </Card>
  );
}

type PlanEntryProps = {
  advice: RotationAdvice;
  plan: RotationPlan;
  entry: RotationPlanCrop;
  candidate?: RotationCandidate;
};

function PlanCard({ advice, plan, entry, candidate }: PlanEntryProps) {
  const { t, i18n } = useTranslation();
  const { search } = useLocation();
  const name = cropNamer(advice);
  const language = i18n.language;
  const { firstSeason, plan: wholePlan } = entry.simulation;
  const { autumn } = entry;
  const establishment = autumn.establishment;

  return (
    <li className="rotation-plan-card">
      <Flex gap={10} align="center" wrap>
        <span className="rotation-rank" aria-label={t('Rank {{rank}}', { rank: entry.rank })}>
          {entry.rank}
        </span>
        <CropIcon crop={name(entry.crop)} size={28} />
        <Typography.Text strong className="rotation-candidate-name">
          {t(name(entry.crop))}
        </Typography.Text>
        {candidate?.isIntended && <Tag color="green">{t('Your crop')}</Tag>}
        <RiskTag candidate={candidate} />
      </Flex>
      <ol className="rotation-plan-sequence" aria-label={t('Crops by season')}>
        {entry.steps.map((step) => (
          <li key={step.season}>
            <Typography.Text type="secondary">{step.season}</Typography.Text>
            <Typography.Text>{t(name(step.crop))}</Typography.Text>
          </li>
        ))}
      </ol>
      <dl className="rotation-stats">
        <div>
          <dt>{t('Chance of a loss in {{year}}', { year: plan.firstSeason })}</dt>
          <dd>{formatPercent(firstSeason.lossProbability, language)}</dd>
        </div>
        <div>
          <dt>{t('Typical result')}</dt>
          <dd>{formatSignedUsd(firstSeason.p50UsdPerAcre, language)}</dd>
        </div>
        <div>
          <dt>{t('Poor year to good year')}</dt>
          <dd>
            {t('{{low}} to {{high}}', {
              low: formatSignedUsd(firstSeason.p10UsdPerAcre, language),
              high: formatSignedUsd(firstSeason.p90UsdPerAcre, language),
            })}
          </dd>
        </div>
        <div>
          <dt>{t('Expected yield')}</dt>
          <dd>
            {formatNumber(firstSeason.yieldPerAcre.meanPerAcre, language)}{' '}
            {firstSeason.yieldPerAcre.unit}
          </dd>
        </div>
        {wholePlan && plan.seasons > 1 && (
          <div className="rotation-stats-full">
            <dt>{t('All {{seasons}} seasons, typical', { seasons: plan.seasons })}</dt>
            <dd>
              {t('{{amount}}, loss in {{share}}', {
                amount: formatSignedUsd(wholePlan.p50UsdPerAcre, language),
                share: formatPercent(wholePlan.lossProbability, language),
              })}
            </dd>
          </div>
        )}
      </dl>
      <Flex gap={8} align="center" wrap className="rotation-plan-autumn">
        <Typography.Text type="secondary">{t('This autumn:')}</Typography.Text>
        <Typography.Text>
          {t(autumnActionLabels[autumn.action] ?? autumn.action)}
          {autumn.species && ` · ${t(name(autumn.species))}`}
        </Typography.Text>
        {establishment && (
          <Tag color={establishmentColors[establishment]}>
            {t(establishmentLabels[establishment])}
          </Tag>
        )}
      </Flex>
      {entry.demoted && (
        <Typography.Text type="secondary">
          {t('Ranked lower: the autumn sowing this plan needs rarely establishes here.')}
        </Typography.Text>
      )}
      <RouterButton
        to={{ pathname: recommendationPath(advice.fieldId, entry.crop), search }}
        icon={<ArrowRight size={16} />}
        iconPlacement="end"
      >
        {t('Forecast and details')}
      </RouterButton>
    </li>
  );
}

function PlanRow({ advice, plan, entry, candidate }: PlanEntryProps) {
  const { t, i18n } = useTranslation();
  const { search } = useLocation();
  const name = cropNamer(advice);
  const { firstSeason } = entry.simulation;

  return (
    <li className="rotation-candidate-row">
      <Flex className="rotation-candidate-summary" gap={12} align="center" wrap>
        <span className="rotation-rank" aria-label={t('Rank {{rank}}', { rank: entry.rank })}>
          {entry.rank}
        </span>
        <Typography.Text strong className="rotation-candidate-name">
          {t(name(entry.crop))}
        </Typography.Text>
        {candidate?.isIntended && <Tag color="green">{t('Your crop')}</Tag>}
        <RiskTag candidate={candidate} />
        <Typography.Text type="secondary">
          {t('Loss in {{share}} of years · typical {{amount}} in {{year}}', {
            share: formatPercent(firstSeason.lossProbability, i18n.language),
            amount: formatSignedUsd(firstSeason.p50UsdPerAcre, i18n.language),
            year: plan.firstSeason,
          })}
        </Typography.Text>
      </Flex>
      <RouterButton
        to={{ pathname: recommendationPath(advice.fieldId, entry.crop), search }}
        icon={<ArrowRight size={18} />}
        aria-label={t('View more about {{crop}}', { crop: t(name(entry.crop)) })}
      />
    </li>
  );
}

type UnpricedRowProps = { advice: RotationAdvice; candidate: RotationCandidate };

function UnpricedRow({ advice, candidate }: UnpricedRowProps) {
  const { t } = useTranslation();
  const { search } = useLocation();
  const reason = candidate.notModelledCode;

  return (
    <li className="rotation-candidate-row">
      <Flex className="rotation-candidate-summary" gap={12} align="center" wrap>
        <Typography.Text strong className="rotation-candidate-name">
          {t(candidate.label)}
        </Typography.Text>
        {candidate.isIntended && <Tag color="green">{t('Your crop')}</Tag>}
        <RiskTag candidate={candidate} />
        {reason && (
          <Typography.Text type="secondary">
            {t(notModelledLabels[reason] ?? reason)}
          </Typography.Text>
        )}
      </Flex>
      <RouterButton
        to={{ pathname: recommendationPath(advice.fieldId, candidate.crop), search }}
        icon={<ArrowRight size={18} />}
        aria-label={t('View more about {{crop}}', { crop: t(candidate.label) })}
      />
    </li>
  );
}

function RiskTag({ candidate }: { candidate?: RotationCandidate }) {
  const { t } = useTranslation();
  if (!candidate) {
    return null;
  }
  const level = highestRiskLevel(candidate);
  if (!level) {
    return <Tag>{t('No risks found')}</Tag>;
  }

  return (
    <Tag color={levelColors[level]}>
      {t('{{level}} · {{risks}} risks', {
        level: t(levelLabels[level]),
        risks: candidate.risks.length,
      })}
    </Tag>
  );
}

function PlanBasis({ plan }: { plan: RotationPlan }) {
  const { t } = useTranslation();
  const codes = distinctGapCodes(plan.gaps);

  return (
    <section className="rotation-plan-section rotation-gaps">
      <Typography.Title level={5}>{t('How the forecast is made')}</Typography.Title>
      <Typography.Paragraph type="secondary">
        {plan.years &&
          t(
            'Each plan is replayed through {{years}} past years ({{first}}–{{last}}) of weather, yields and prices in today’s dollars.',
            { years: plan.years.count, first: plan.years.first, last: plan.years.last },
          )}{' '}
        {plan.yearOdds?.method === 'analog_years'
          ? t('Years that resemble the current drought and price situation count more.')
          : t('Every past year counts equally.')}{' '}
        {t('The chances are how often it happened, not a promise for next year.')}
      </Typography.Paragraph>
      {codes.length > 0 && (
        <ul>
          {codes.map((code) => (
            <li key={code}>
              <Typography.Text type="secondary">{t(planGapLabels[code] ?? code)}</Typography.Text>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
