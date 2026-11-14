import { Flex, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import type { RotationFinding } from '../../../types/rotation/rotation.types.ts';
import {
  categoryLabels,
  evidenceLabels,
  factLabels,
  levelColors,
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
          <li key={finding.ruleId} className={`rotation-finding rotation-finding-${finding.kind}`}>
            <Flex gap={8} wrap align="center">
              <Typography.Text strong>{t(finding.title)}</Typography.Text>
              {finding.level && (
                <Tag color={levelColors[finding.level]}>{t(levelLabels[finding.level])}</Tag>
              )}
              <Tag>{t(categoryLabels[finding.category] ?? finding.category)}</Tag>
            </Flex>
            <FindingReason finding={finding} cropLabels={cropLabels} />
            <Typography.Text type="secondary" className="rotation-finding-evidence">
              {finding.evidenceStrength &&
                `${t(evidenceLabels[finding.evidenceStrength] ?? finding.evidenceStrength)}${finding.needsLocalReview ? ' · ' : ''}`}
              {finding.needsLocalReview && t('Check with a local agronomist')}
            </Typography.Text>
          </li>
        ))}
      </ul>
    </section>
  );
}

type FindingReasonProps = { finding: RotationFinding; cropLabels: Record<string, string> };

function FindingReason({ finding, cropLabels }: FindingReasonProps) {
  const { t, i18n } = useTranslation();
  const { trigger } = finding;
  if (trigger.type === 'hazard') {
    return (
      <Typography.Paragraph className="rotation-finding-reason">
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
        )}{' '}
        {trigger.worstYear !== null &&
          trigger.worstValue !== null &&
          t('Worst season: {{year}} ({{value}}).', {
            year: trigger.worstYear,
            value: formatValue(trigger.worstValue, t, i18n.language),
          })}
      </Typography.Paragraph>
    );
  }

  return (
    <Typography.Paragraph className="rotation-finding-reason">
      {trigger.conditions
        .filter((condition) => condition.fact !== 'candidate.crop')
        .map(
          (condition) =>
            `${t(factLabels[condition.fact] ?? condition.fact)}: ${formatValue(condition.actual, t, i18n.language, cropLabels)}`,
        )
        .join(' · ')}
    </Typography.Paragraph>
  );
}
