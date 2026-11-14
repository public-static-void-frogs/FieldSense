import { useQuery } from '@tanstack/react-query';
import { Button, Card, Flex, Popover, Skeleton, Tag, Typography } from 'antd';
import { ArrowRight, Award, CircleAlert, CircleCheck, Medal, Trophy } from 'lucide-react';
import { useId } from 'react';
import { useTranslation } from 'react-i18next';
import { rotationQueries } from '../../../api/rotation/rotation.queries.ts';
import { CropIcon } from '../../../components/common/CropIcon';
import { RouterButton } from '../../../components/common/RouterButton';
import type { RotationCandidate } from '../../../types/rotation/rotation.types.ts';
import { levelColors, levelLabels } from '../../rotation/constants/rotationLabels.ts';
import {
  formatUsd,
  highestRiskLevel,
  rankedCandidates,
  sortedFindings,
} from '../../rotation/utils/rotationPresentation.ts';
import { recommendationPath } from '../../rotation/utils/rotationRoutes.ts';
import './FieldRecommendation.css';

const previewLimit = 3;
const rankIcons = [Trophy, Medal, Award];

type FieldRecommendationProps = { fieldId: string };

export function FieldRecommendation({ fieldId }: FieldRecommendationProps) {
  const { t } = useTranslation();
  const {
    data: advice,
    isPending,
    isError,
    refetch,
  } = useQuery({
    ...rotationQueries.advice({ fieldId, priorities: [] }),
    placeholderData: undefined,
  });
  const titleId = useId();
  const candidates = advice ? rankedCandidates(advice) : [];
  const remaining = candidates.length - previewLimit;

  return (
    <section className="field-strategies" aria-labelledby={titleId}>
      <Typography.Title level={3} id={titleId}>
        {t('Crop strategies for next season')}
      </Typography.Title>
      {isPending && <Skeleton active />}
      {!isPending && candidates.length === 0 && (
        <Flex gap={12} align="center" wrap>
          <Typography.Text type="secondary">
            {isError
              ? t('The recommendation could not be loaded')
              : t('No crop recommendations are available for this field.')}
          </Typography.Text>
          {isError && <Button onClick={() => void refetch()}>{t('Try again')}</Button>}
        </Flex>
      )}
      {candidates.length > 0 && (
        <div className="field-strategies-grid">
          {candidates.slice(0, previewLimit).map((candidate) => (
            <CropStrategyCard key={candidate.crop} candidate={candidate} fieldId={fieldId} />
          ))}
        </div>
      )}
      {remaining > 0 && (
        <RouterButton
          className="field-strategies-explore"
          to={recommendationPath(fieldId)}
          icon={<ArrowRight size={16} />}
          iconPlacement="end"
        >
          {t('Explore {{count}}+ more strategies', { count: remaining })}
        </RouterButton>
      )}
    </section>
  );
}

type CropStrategyCardProps = { candidate: RotationCandidate; fieldId: string };

function CropStrategyCard({ candidate, fieldId }: CropStrategyCardProps) {
  const { t, i18n } = useTranslation();
  const level = highestRiskLevel(candidate);
  const [risk] = sortedFindings(candidate.risks);
  const [benefit] = sortedFindings(candidate.benefits);
  const RankIcon = rankIcons[candidate.rank - 1] ?? Medal;

  return (
    <Card className="field-strategy-card">
      <div className="field-strategy-banner">
        <span className="field-strategy-icon">
          <CropIcon crop={candidate.label} size={38} />
        </span>
        <Popover
          placement="top"
          trigger={['hover', 'click']}
          content={
            <div className="field-strategy-rank-info">
              <Typography.Text>{t('Rank is based on the system prediction.')}</Typography.Text>
              <RouterButton type="link" to={recommendationPath(fieldId)}>
                {t('Learn more')}
              </RouterButton>
            </div>
          }
        >
          <button className="field-strategy-rank" type="button" data-rank={candidate.rank}>
            <RankIcon size={16} aria-hidden="true" />
            {t('Rank {{rank}}', { rank: candidate.rank })}
          </button>
        </Popover>
      </div>
      <div className="field-strategy-content">
        <Typography.Title level={4}>{t(candidate.label)}</Typography.Title>
        {level ? (
          <Tag color={levelColors[level]}>{t(levelLabels[level])}</Tag>
        ) : (
          candidate.risks.length === 0 && <Tag>{t('No risks found')}</Tag>
        )}
        {(benefit || risk) && (
          <ul className="field-strategy-findings">
            {benefit && (
              <li>
                <CircleCheck className="field-strategy-benefit-icon" size={17} aria-hidden="true" />
                <div>
                  <span>{t('Benefit')}</span>
                  <Typography.Text>{t(benefit.title)}</Typography.Text>
                </div>
              </li>
            )}
            {risk && (
              <li>
                <CircleAlert className="field-strategy-risk-icon" size={17} aria-hidden="true" />
                <div>
                  <span>{t('Risk')}</span>
                  <Typography.Text>{t(risk.title)}</Typography.Text>
                </div>
              </li>
            )}
          </ul>
        )}
      </div>
      <div className="field-strategy-footer">
        <dl className="field-strategy-revenue">
          <dt>{t('Estimated gross revenue')}</dt>
          <dd>
            {candidate.revenue
              ? formatUsd(candidate.revenue.midUsd, i18n.language)
              : t('Not available')}
          </dd>
        </dl>
        <RouterButton
          block
          className="field-strategy-link"
          to={recommendationPath(fieldId, candidate.crop)}
          aria-label={t('View more about {{crop}}', { crop: t(candidate.label) })}
        >
          {t('View more')}
        </RouterButton>
      </div>
    </Card>
  );
}
