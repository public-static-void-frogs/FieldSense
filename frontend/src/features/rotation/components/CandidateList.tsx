import { Collapse, Flex, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import type { RotationAdvice, RotationCandidate } from '../../../types/rotation/rotation.types.ts';
import { levelColors, levelLabels } from '../constants/rotationLabels.ts';
import {
  formatNumber,
  formatUsd,
  highestRiskLevel,
  rankedCandidates,
} from '../utils/rotationPresentation.ts';
import { CandidateDetails } from './CandidateDetails';

type CandidateListProps = { advice: RotationAdvice };

export function CandidateList({ advice }: CandidateListProps) {
  const candidates = rankedCandidates(advice);
  const open = candidates
    .filter((candidate) => candidate.isIntended || candidate.rank === 1)
    .map((candidate) => candidate.crop);

  return (
    <Collapse
      // Re-open the relevant crops when another intended crop is chosen.
      key={advice.intendedCrop}
      className="rotation-candidates"
      defaultActiveKey={open}
      items={candidates.map((candidate) => ({
        key: candidate.crop,
        label: <CandidateSummary candidate={candidate} />,
        children: <CandidateDetails advice={advice} candidate={candidate} />,
      }))}
    />
  );
}

type CandidateSummaryProps = { candidate: RotationCandidate };

function CandidateSummary({ candidate }: CandidateSummaryProps) {
  const { t, i18n } = useTranslation();
  const level = highestRiskLevel(candidate);

  return (
    <Flex className="rotation-candidate-summary" gap={12} align="center" wrap>
      <span className="rotation-rank" aria-label={t('Rank {{rank}}', { rank: candidate.rank })}>
        {candidate.rank}
      </span>
      <Typography.Text strong className="rotation-candidate-name">
        {t(candidate.label)}
      </Typography.Text>
      {candidate.isIntended && <Tag color="green">{t('Your crop')}</Tag>}
      {level ? (
        <Tag color={levelColors[level]}>{t(levelLabels[level])}</Tag>
      ) : (
        <Tag>{t('No risks found')}</Tag>
      )}
      <Typography.Text type="secondary">
        {t('{{risks}} risks · {{benefits}} benefits · {{points}} points', {
          risks: candidate.risks.length,
          benefits: candidate.benefits.length,
          points: formatNumber(candidate.score, i18n.language),
        })}
      </Typography.Text>
      {candidate.revenue && (
        <Typography.Text className="rotation-candidate-revenue">
          {t('about {{amount}} gross', {
            amount: formatUsd(candidate.revenue.midUsd, i18n.language),
          })}
        </Typography.Text>
      )}
    </Flex>
  );
}
