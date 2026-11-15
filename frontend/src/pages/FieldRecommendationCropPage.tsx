import { useSuspenseQuery } from '@tanstack/react-query';
import { Button, Card, Result, Skeleton } from 'antd';
import { ArrowLeft } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useLoaderData, useLocation } from 'react-router-dom';
import { fieldQueries } from '../api/fields/fields.queries.ts';
import type { RecommendationCropRouteData } from '../app/route-loaders.ts';
import { CropIcon } from '../components/common/CropIcon';
import { PageHeading } from '../components/common/PageHeading';
import { RouterButton } from '../components/common/RouterButton';
import { FieldStrategySection } from '../features/planning/components/FieldStrategySection';
import { CandidateDetails } from '../features/rotation/components/CandidateDetails';
import { useRotationAdvice } from '../features/rotation/hooks/useRotationAdvice.ts';
import { recommendationPath } from '../features/rotation/utils/rotationRoutes.ts';
import '../styles/rotation.css';

export function FieldRecommendationCropPage() {
  const { t } = useTranslation();
  const { fieldId, cropId } = useLoaderData<RecommendationCropRouteData>();
  const { search } = useLocation();
  const { advice, isLoading, error, retry } = useRotationAdvice(fieldId);
  const { data: field } = useSuspenseQuery(fieldQueries.byId(fieldId));
  const candidate = advice?.candidates.find(({ crop }) => crop === cropId);
  const recommendation = { pathname: recommendationPath(fieldId), search };
  const backLabel = t('Back to crop recommendations');

  if (isLoading) {
    return (
      <Card>
        <Skeleton active paragraph={{ rows: 6 }} />
      </Card>
    );
  }

  if (error && !advice) {
    return (
      <Result
        status="warning"
        title={t('The recommendation could not be loaded')}
        extra={[
          <RouterButton key="back" to={recommendation}>
            {backLabel}
          </RouterButton>,
          <Button key="retry" type="primary" onClick={() => void retry()}>
            {t('Try again')}
          </Button>,
        ]}
      />
    );
  }

  if (!field || !advice || !candidate) {
    return (
      <Result
        status="404"
        title={field && advice ? t('Strategy not found') : t('Field not found')}
        extra={<RouterButton to={recommendation}>{backLabel}</RouterButton>}
      />
    );
  }

  return (
    <div className="rotation-page rotation-strategy-page">
      <PageHeading
        title={
          <>
            {field.crop || field.name} <span aria-hidden="true">·</span> {t('Recommendations')}{' '}
            <span aria-hidden="true">·</span>{' '}
            <span className="rotation-strategy-title-crop">
              <CropIcon crop={candidate.label} size={36} />
              {t('{{crop}} Strategy', { crop: t(candidate.label) })}
            </span>
          </>
        }
        eyebrow=""
        description={t('Ranked {{rank}} out of {{total}} crops for this field', {
          rank: candidate.rank,
          total: advice.candidates.length,
        })}
        titlePrefix={
          <>
            <RouterButton
              type="text"
              icon={<ArrowLeft size={20} />}
              aria-label={backLabel}
              to={recommendation}
            />
            {field.crop && <CropIcon crop={field.crop} size={36} />}
          </>
        }
      />
      <div className="rotation-stack">
        <Card>
          <CandidateDetails advice={advice} candidate={candidate} />
        </Card>
        <FieldStrategySection fieldId={fieldId} cropLabel={candidate.label} />
      </div>
    </div>
  );
}
