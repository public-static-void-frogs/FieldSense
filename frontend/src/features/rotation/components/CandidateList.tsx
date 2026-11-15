import { Button, Flex, Tag, Tooltip, Typography } from 'antd';
import { CircleHelp } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useLocation } from 'react-router-dom';
import { CropIcon } from '../../../components/common/CropIcon';
import { RouterButton } from '../../../components/common/RouterButton';
import type { RotationAdvice, RotationCandidate } from '../../../types/rotation/rotation.types.ts';
import { levelLabels } from '../constants/rotationLabels.ts';
import {
  formatNumber,
  formatUsd,
  highestRiskLevel,
  rankedCandidates,
} from '../utils/rotationPresentation.ts';
import { recommendationPath } from '../utils/rotationRoutes.ts';

type CandidateListProps = { advice: RotationAdvice };

export function CandidateList({ advice }: CandidateListProps) {
  const { t, i18n } = useTranslation();
  const { search } = useLocation();
  const candidates = rankedCandidates(advice);

  if (candidates.length === 0) {
    return (
      <Typography.Text type="secondary">
        {t('No crop recommendations are available for this field.')}
      </Typography.Text>
    );
  }

  return (
    <ol className="rotation-candidates" role="list">
      {candidates.map((candidate) => (
        <li className="rotation-candidate-row" key={candidate.crop} data-rank={candidate.rank}>
          <CandidateSummary candidate={candidate} />
          <div className="rotation-candidate-actions">
            {candidate.revenue && (
              <div className="rotation-candidate-revenue">
                <strong>{formatUsd(candidate.revenue.midUsd, i18n.language)}</strong>
                <span>{t('Estimated gross revenue')}</span>
              </div>
            )}
            <RouterButton
              to={{ pathname: recommendationPath(advice.fieldId, candidate.crop), search }}
              aria-label={t('View details for {{crop}}', { crop: t(candidate.label) })}
            >
              {t('View details')}
            </RouterButton>
          </div>
        </li>
      ))}
    </ol>
  );
}

type CandidateSummaryProps = { candidate: RotationCandidate };

function CandidateSummary({ candidate }: CandidateSummaryProps) {
  const { t, i18n } = useTranslation();
  const level = highestRiskLevel(candidate);

  return (
    <div className="rotation-candidate-summary">
      <span className="rotation-rank" aria-label={t('Rank {{rank}}', { rank: candidate.rank })}>
        {candidate.rank}
      </span>
      <CropIcon crop={candidate.label} size={32} />
      <Flex gap={8} align="center" wrap>
        <Typography.Text strong className="rotation-candidate-name">
          {t(candidate.label)}
        </Typography.Text>
        {candidate.isIntended && (
          <Tag className="rotation-candidate-badge" data-tone="intended">
            {t('Your crop')}
          </Tag>
        )}
        {level && (
          <Tag className="rotation-candidate-badge" data-tone={level}>
            {t(levelLabels[level])}
          </Tag>
        )}
        <Tooltip
          trigger={['hover', 'focus', 'click']}
          title={t('{{risks}} risks · {{benefits}} benefits · {{points}} points', {
            risks: candidate.risks.length,
            benefits: candidate.benefits.length,
            points: formatNumber(candidate.score, i18n.language),
          })}
        >
          <Button
            type="text"
            size="small"
            shape="circle"
            icon={<CircleHelp size={16} />}
            aria-label={t('Ranking information for {{crop}}', { crop: t(candidate.label) })}
          />
        </Tooltip>
      </Flex>
    </div>
  );
}
