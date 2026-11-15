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
        <CandidateRow
          key={candidate.crop}
          fieldId={advice.fieldId}
          crop={candidate.crop}
          label={candidate.label}
          candidate={candidate}
          amount={
            candidate.revenue && {
              value: formatUsd(candidate.revenue.midUsd, i18n.language),
              label: t('Estimated gross revenue'),
            }
          }
        />
      ))}
    </ol>
  );
}

type CandidateRowProps = {
  fieldId: string;
  crop: string;
  label: string;
  candidate?: RotationCandidate;
  rank?: number;
  amount?: { value: string; label: string } | null;
  description?: string;
  tooltipNote?: string;
};

export function CandidateRow({
  fieldId,
  crop,
  label,
  candidate,
  rank = candidate?.rank,
  amount,
  description,
  tooltipNote,
}: CandidateRowProps) {
  const { t } = useTranslation();
  const { search } = useLocation();
  const cropLabel = t(label);

  return (
    <li className="rotation-candidate-row" data-rank={rank}>
      <CandidateSummary
        label={label}
        candidate={candidate}
        rank={rank}
        description={description}
        tooltipNote={tooltipNote}
      />
      <div className="rotation-candidate-actions">
        {amount && (
          <div className="rotation-candidate-revenue">
            <strong>{amount.value}</strong>
            <span>{amount.label}</span>
          </div>
        )}
        <RouterButton
          to={{ pathname: recommendationPath(fieldId, crop), search }}
          aria-label={t('View details for {{crop}}', { crop: cropLabel })}
        >
          {t('View details')}
        </RouterButton>
      </div>
    </li>
  );
}

type CandidateSummaryProps = Pick<
  CandidateRowProps,
  'label' | 'candidate' | 'rank' | 'description' | 'tooltipNote'
> & { showNoRisks?: boolean };

export function CandidateSummary({
  label,
  candidate,
  rank,
  description,
  tooltipNote,
  showNoRisks = false,
}: CandidateSummaryProps) {
  const { t, i18n } = useTranslation();
  const level = candidate && highestRiskLevel(candidate);
  const cropLabel = t(label);

  return (
    <div className="rotation-candidate-summary">
      {rank != null && (
        <span className="rotation-rank" aria-label={t('Rank {{rank}}', { rank })}>
          {rank}
        </span>
      )}
      <CropIcon crop={label} size={32} />
      <Flex gap={8} align="center" wrap>
        <Typography.Text strong className="rotation-candidate-name">
          {cropLabel}
        </Typography.Text>
        {candidate?.isIntended && (
          <Tag className="rotation-candidate-badge" data-tone="intended">
            {t('Your crop')}
          </Tag>
        )}
        {level && (
          <Tag className="rotation-candidate-badge" data-tone={level}>
            {t(levelLabels[level])}
          </Tag>
        )}
        {showNoRisks && candidate && !level && (
          <Tag className="rotation-candidate-badge">{t('No risks found')}</Tag>
        )}
        {candidate && (
          <Tooltip
            trigger={['hover', 'focus', 'click']}
            title={
              <>
                <div>
                  {t('{{risks}} risks · {{benefits}} benefits · {{points}} points', {
                    risks: candidate.risks.length,
                    benefits: candidate.benefits.length,
                    points: formatNumber(candidate.score, i18n.language),
                  })}
                </div>
                {tooltipNote && <div>{tooltipNote}</div>}
              </>
            }
          >
            <Button
              type="text"
              size="small"
              shape="circle"
              icon={<CircleHelp size={16} />}
              aria-label={t('Ranking information for {{crop}}', { crop: cropLabel })}
            />
          </Tooltip>
        )}
        {description && (
          <Typography.Text type="secondary" className="rotation-candidate-description">
            {description}
          </Typography.Text>
        )}
      </Flex>
    </div>
  );
}
