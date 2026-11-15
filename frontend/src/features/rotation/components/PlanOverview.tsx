import { Card, Tag, Typography } from 'antd';
import { ArrowRight, ChevronDown } from 'lucide-react';
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
import { distinctGapCodes, formatNumber, formatPercent } from '../utils/rotationPresentation.ts';
import { recommendationPath } from '../utils/rotationRoutes.ts';
import { CandidateRow, CandidateSummary } from './CandidateList';

type PlanOverviewProps = { advice: RotationAdvice; plan: RotationPlan };

export function PlanOverview({ advice, plan }: PlanOverviewProps) {
  const { t, i18n } = useTranslation();
  const crops = rankedPlanCrops(plan);
  const top = crops.filter(({ tier }) => tier === 'top');
  const others = crops.filter(({ tier }) => tier !== 'top');
  const unpriced = unpricedCandidates(advice, plan);
  const candidates = new Map(advice.candidates.map((candidate) => [candidate.crop, candidate]));
  const name = cropNamer(advice);
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
      {plan.method === 'learned_policy' && (
        <Typography.Paragraph type="secondary">
          {t(
            'These plans were chosen by the learned planner. Each plan breakdown shows how it compares with the exact calculation.',
          )}
        </Typography.Paragraph>
      )}
      {plan.planner && plan.planner.used !== plan.planner.requested && (
        <Typography.Paragraph type="secondary">
          {t(
            'The learned planner is not available on this server, so the exact calculation was used.',
          )}
        </Typography.Paragraph>
      )}
      <ol className="rotation-plan-top" role="list">
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
          <ol className="rotation-candidates" role="list">
            {others.map(({ crop, rank, simulation: { firstSeason } }) => (
              <CandidateRow
                key={crop}
                fieldId={advice.fieldId}
                crop={crop}
                label={name(crop)}
                rank={rank}
                candidate={candidates.get(crop)}
                description={
                  typeof firstSeason.operatingLossProbability === 'number'
                    ? t(
                        'Operating costs not covered in {{share}} of years, all costs in {{full}} · typical {{amount}} after all costs in {{year}}',
                        {
                          share: formatPercent(firstSeason.operatingLossProbability, i18n.language),
                          full: formatPercent(firstSeason.lossProbability, i18n.language),
                          amount: formatSignedUsd(firstSeason.p50UsdPerAcre, i18n.language),
                          year: plan.firstSeason,
                        },
                      )
                    : t('Loss in {{share}} of years · typical {{amount}} in {{year}}', {
                        share: formatPercent(firstSeason.lossProbability, i18n.language),
                        amount: formatSignedUsd(firstSeason.p50UsdPerAcre, i18n.language),
                        year: plan.firstSeason,
                      })
                }
              />
            ))}
          </ol>
        </section>
      )}
      {unpriced.length > 0 && (
        <section className="rotation-plan-section">
          <Typography.Title level={5}>{t('Not priced, rotation risk only')}</Typography.Title>
          <ol className="rotation-candidates" role="list">
            {unpriced.map((candidate) => (
              <CandidateRow
                key={candidate.crop}
                fieldId={advice.fieldId}
                crop={candidate.crop}
                label={candidate.label}
                candidate={candidate}
                tooltipNote={
                  candidate.notModelledCode
                    ? t(notModelledLabels[candidate.notModelledCode] ?? candidate.notModelledCode)
                    : undefined
                }
              />
            ))}
          </ol>
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
      <div className="rotation-candidate-row rotation-plan-card-header" data-rank={entry.rank}>
        <CandidateSummary
          label={name(entry.crop)}
          rank={entry.rank}
          candidate={candidate}
          showNoRisks
        />
        <RouterButton
          to={{ pathname: recommendationPath(advice.fieldId, entry.crop), search }}
          icon={<ArrowRight size={16} />}
          iconPlacement="end"
        >
          {t('Forecast and details')}
        </RouterButton>
      </div>
      <div className="rotation-plan-card-body">
        <ol className="rotation-plan-sequence" role="list" aria-label={t('Crops by season')}>
          {entry.steps.map(({ season, crop }) => {
            const label = name(crop);

            return (
              <li key={season}>
                <time dateTime={String(season)}>{season}</time>
                <span className="rotation-plan-season-crop">
                  <CropIcon crop={label} size={28} />
                  <span>{t(label)}</span>
                </span>
              </li>
            );
          })}
        </ol>
        <details className="rotation-plan-disclosure">
          <summary>
            <ChevronDown size={16} aria-hidden="true" />
            {t('Plan breakdown')}
          </summary>
          <dl className="rotation-plan-facts">
            {typeof firstSeason.operatingLossProbability === 'number' ? (
              <>
                <div>
                  <dt>
                    {t('Chance of not covering operating costs in {{year}}', {
                      year: plan.firstSeason,
                    })}
                  </dt>
                  <dd>{formatPercent(firstSeason.operatingLossProbability, language)}</dd>
                </div>
                <div>
                  <dt>
                    {t('Chance of not covering all costs in {{year}}', { year: plan.firstSeason })}
                  </dt>
                  <dd>{formatPercent(firstSeason.lossProbability, language)}</dd>
                </div>
              </>
            ) : (
              <div>
                <dt>{t('Chance of a loss in {{year}}', { year: plan.firstSeason })}</dt>
                <dd>{formatPercent(firstSeason.lossProbability, language)}</dd>
              </div>
            )}
            <div>
              <dt>{t('Typical result after all costs')}</dt>
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
              <div>
                <dt>{t('All {{seasons}} seasons, typical', { seasons: plan.seasons })}</dt>
                <dd>
                  {typeof wholePlan.operatingLossProbability === 'number'
                    ? t(
                        '{{amount}}, operating costs not covered in {{share}}, all costs in {{full}}',
                        {
                          amount: formatSignedUsd(wholePlan.p50UsdPerAcre, language),
                          share: formatPercent(wholePlan.operatingLossProbability, language),
                          full: formatPercent(wholePlan.lossProbability, language),
                        },
                      )
                    : t('{{amount}}, loss in {{share}}', {
                        amount: formatSignedUsd(wholePlan.p50UsdPerAcre, language),
                        share: formatPercent(wholePlan.lossProbability, language),
                      })}
                </dd>
              </div>
            )}
            {typeof entry.belowOptimumUsdPerAcre === 'number' && (
              <div>
                <dt>{t('Against the exact calculation')}</dt>
                <dd>
                  {entry.belowOptimumUsdPerAcre < 0.5
                    ? t('Same result')
                    : t('{{amount}} per acre lower over the plan', {
                        amount: formatSignedUsd(entry.belowOptimumUsdPerAcre, language),
                      })}
                </dd>
              </div>
            )}
            <div>
              <dt>{t('This autumn')}</dt>
              <dd>
                {t(autumnActionLabels[autumn.action] ?? autumn.action)}
                {autumn.species && ` · ${t(name(autumn.species))}`}
                {establishment && (
                  <Tag color={establishmentColors[establishment]}>
                    {t(establishmentLabels[establishment])}
                  </Tag>
                )}
              </dd>
            </div>
            {entry.demoted && (
              <div>
                <dt>{t('Ranked lower')}</dt>
                <dd>{t('The autumn sowing this plan needs rarely establishes here.')}</dd>
              </div>
            )}
          </dl>
        </details>
      </div>
    </li>
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
