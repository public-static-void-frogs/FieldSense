import { Typography } from 'antd';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import type { RotationFinding } from '../../../types/rotation/rotation.types.ts';
import {
  categoryLabels,
  evidenceLabels,
  factLabels,
  levelLabels,
  metricLabels,
  stageLabels,
} from '../constants/rotationLabels.ts';
import {
  formatIsoDay,
  formatPercent,
  formatValue,
  sortedFindings,
} from '../utils/rotationPresentation.ts';

type FindingListProps = {
  title: string;
  findings: RotationFinding[];
  cropLabels: Record<string, string>;
};

export function FindingList({ title, findings, cropLabels }: FindingListProps) {
  const { t } = useTranslation();
  if (findings.length === 0) {
    return null;
  }

  return (
    <section className="rotation-findings">
      <Typography.Title level={5}>{title}</Typography.Title>
      <ul>
        {sortedFindings(findings).map((finding) => (
          <li
            key={finding.ruleId}
            className="rotation-finding"
            data-kind={finding.kind}
            data-risk={finding.level}
          >
            <div className="rotation-finding-main">
              <div className="rotation-finding-heading">
                <Typography.Text strong>{t(finding.title)}</Typography.Text>
                <span className="rotation-finding-category">
                  {t(categoryLabels[finding.category] ?? finding.category)}
                </span>
                {finding.level && (
                  <span className="rotation-finding-level">{t(levelLabels[finding.level])}</span>
                )}
              </div>
              <FindingReason finding={finding} cropLabels={cropLabels} />
            </div>
            <div className="rotation-finding-evidence">
              <EvidenceStrength strength={finding.evidenceStrength} />
              {finding.needsLocalReview && (
                <Typography.Text type="secondary">
                  {t('Check with a local agronomist')}
                </Typography.Text>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

const evidenceSteps = { weak: 1, moderate: 2, strong: 3 };

function EvidenceStrength({ strength }: { strength: string | null }) {
  const { t } = useTranslation();
  const steps = evidenceSteps[strength as keyof typeof evidenceSteps] ?? 0;

  return (
    <div className="rotation-evidence" data-strength={strength}>
      <span className="rotation-evidence-scale" aria-hidden="true">
        {[1, 2, 3].map((step) => (
          <span key={step} data-filled={step <= steps} />
        ))}
      </span>
      <strong>
        {strength ? t(evidenceLabels[strength] ?? strength) : t('Evidence strength unavailable')}
      </strong>
    </div>
  );
}

type HazardTrigger = Extract<RotationFinding['trigger'], { type: 'hazard' }>;

/** Why the hazard has its level: the measured yield cost, or that none is measured. */
function hazardCost(trigger: HazardTrigger, t: TFunction, language: string): string {
  const measured = trigger.lossWhenHit;
  if (trigger.levelBasis !== 'loss' || !measured) {
    return t(
      'How much yield it costs is not measured for this crop, so the level reflects only how often it happens.',
    );
  }
  if (measured.loss <= 0) {
    return t('County yields of this crop show no loss in the seasons when it happens.');
  }
  return t(
    'In a season when it happens, county yields of this crop were about {{loss}} lower, so it is expected to cost about {{expected}} of the yield per season.',
    {
      loss: formatPercent(measured.loss, language),
      expected: formatPercent(trigger.expectedLoss ?? 0, language),
    },
  );
}

type FindingReasonProps = { finding: RotationFinding; cropLabels: Record<string, string> };

function FindingReason({ finding, cropLabels }: FindingReasonProps) {
  const { t, i18n } = useTranslation();
  const { trigger } = finding;
  if (trigger.type === 'hazard') {
    return (
      <div className="rotation-finding-weather">
        <p>
          {t(
            'In {{hit}} of {{total}} recent seasons, around {{stage}} ({{start}} – {{end}}): {{metric}}.',
            {
              hit: trigger.seasonsHit,
              total: trigger.seasonsTotal,
              stage: t(stageLabels[trigger.stage] ?? trigger.stage).toLowerCase(),
              start: formatIsoDay(trigger.window.startDate, i18n.language),
              end: formatIsoDay(trigger.window.endDate, i18n.language),
              metric: t(metricLabels[trigger.metric] ?? trigger.metric),
            },
          )}
        </p>
        {trigger.seasonsTotal > 0 && (
          <progress aria-hidden="true" value={trigger.seasonsHit} max={trigger.seasonsTotal} />
        )}
        {trigger.worstYear !== null && trigger.worstValue !== null && (
          <Typography.Text type="secondary">
            {t('Worst season: {{year}} ({{value}}).', {
              year: trigger.worstYear,
              value: formatValue(trigger.worstValue, t, i18n.language),
            })}
          </Typography.Text>
        )}
        {finding.kind === 'risk' && trigger.levelBasis && (
          <Typography.Text type="secondary">
            {hazardCost(trigger, t, i18n.language)}
          </Typography.Text>
        )}
      </div>
    );
  }

  const facts = new Map(
    trigger.conditions
      .filter(({ fact }) => fact !== 'candidate.crop')
      .map(({ fact, actual }) => [fact, actual]),
  );
  if (facts.size === 0) {
    return null;
  }

  return (
    <dl className="rotation-finding-facts">
      {[...facts].map(([fact, value]) => (
        <div key={fact}>
          <dt>{t(factLabels[fact] ?? fact)}: </dt>
          <dd>{formatValue(value, t, i18n.language, cropLabels)}</dd>
        </div>
      ))}
    </dl>
  );
}
