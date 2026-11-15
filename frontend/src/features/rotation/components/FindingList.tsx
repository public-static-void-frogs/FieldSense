import { Typography } from 'antd';
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
import { formatIsoDay, formatValue, sortedFindings } from '../utils/rotationPresentation.ts';

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

type FindingReasonProps = { finding: RotationFinding; cropLabels: Record<string, string> };

function FindingReason({ finding, cropLabels }: FindingReasonProps) {
  const { t, i18n } = useTranslation();
  const { trigger } = finding;
  if (trigger.type === 'hazard') {
    return (
      <details className="strategy-disclosure rotation-finding-weather">
        <summary>{t('Details')}</summary>
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
      </details>
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
    <details className="strategy-disclosure">
      <summary>{t('Details')}</summary>
      <dl className="rotation-finding-facts">
        {[...facts].map(([fact, value]) => (
          <div key={fact}>
            <dt>{t(factLabels[fact] ?? fact)}: </dt>
            <dd>{formatValue(value, t, i18n.language, cropLabels)}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
