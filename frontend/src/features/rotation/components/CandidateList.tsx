import { Flex, Tag, Typography } from 'antd';
import { ArrowRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useLocation } from 'react-router-dom';
import { RouterButton } from '../../../components/common/RouterButton';
import type { RotationAdvice, RotationCandidate } from '../../../types/rotation/rotation.types.ts';
import { levelColors, levelLabels } from '../constants/rotationLabels.ts';
import {
  formatNumber,
  formatUsd,
  highestRiskLevel,
  rankedCandidates,
} from '../utils/rotationPresentation.ts';
import { recommendationPath } from '../utils/rotationRoutes.ts';

type CandidateListProps = { advice: RotationAdvice };

export function CandidateList({ advice }: CandidateListProps) {
  const { t } = useTranslation();
  const { search } = useLocation();
  const candidates = rankedCandidates(advice);

  return (
    <ul className="rotation-candidates">
      {candidates.map((candidate) => (
        <li className="rotation-candidate-row" key={candidate.crop}>
          <CandidateSummary candidate={candidate} />
          <RouterButton
            to={{ pathname: recommendationPath(advice.fieldId, candidate.crop), search }}
            icon={<ArrowRight size={18} />}
            aria-label={t('View more about {{crop}}', { crop: t(candidate.label) })}
          />
        </li>
      ))}
    </ul>
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
