import { useSuspenseQuery } from '@tanstack/react-query';
import { Button, Card, Result, Skeleton } from 'antd';
import { ArrowLeft } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useLoaderData } from 'react-router-dom';
import { fieldQueries } from '../api/fields/fields.queries.ts';
import type { FieldRouteData } from '../app/route-loaders.ts';
import { PageHeading } from '../components/common/PageHeading';
import { RouterButton } from '../components/common/RouterButton';
import { AdviceControls } from '../features/rotation/components/AdviceControls';
import { AdviceVerdict } from '../features/rotation/components/AdviceVerdict';
import { CandidateList } from '../features/rotation/components/CandidateList';
import { CropHistoryStrip } from '../features/rotation/components/CropHistoryStrip';
import { InformationGaps } from '../features/rotation/components/InformationGaps';
import { OffSeasonCard } from '../features/rotation/components/OffSeasonCard';
import { useRotationAdvice } from '../features/rotation/hooks/useRotationAdvice.ts';
import { seasonYear } from '../features/rotation/utils/rotationPresentation.ts';
import '../styles/rotation.css';

export function FieldRecommendationPage() {
  const { t } = useTranslation();
  const { fieldId } = useLoaderData<FieldRouteData>();
  const { data: field } = useSuspenseQuery(fieldQueries.byId(fieldId));
  const { advice, isLoading, isUpdating, error, retry, priorities, setCrop, togglePriority } =
    useRotationAdvice(fieldId);
  if (!field || advice === null) {
    return (
      <Result
        status="404"
        title={t('Field not found')}
        subTitle={t('This field may have been removed from your farm.')}
        extra={
          <RouterButton type="primary" to="/fields">
            {t('Back to my fields')}
          </RouterButton>
        }
      />
    );
  }

  return (
    <div className="rotation-page">
      <PageHeading
        title={t('Crop recommendation')}
        eyebrow={field.crop || field.name}
        description={
          advice
            ? t(
                'Candidate crops for the {{year}} season, ranked by rotation risk on this field. The lowest risk comes first.',
                { year: seasonYear(advice) },
              )
            : undefined
        }
        titlePrefix={
          <RouterButton
            type="text"
            icon={<ArrowLeft size={20} />}
            aria-label={t('Back to field')}
            to={`/fields/${field.id}`}
          />
        }
      />
      {isLoading && (
        <Card>
          <Skeleton active paragraph={{ rows: 6 }} />
        </Card>
      )}
      {error && !advice && (
        <Result
          status="warning"
          title={t('The recommendation could not be loaded')}
          extra={<Button onClick={() => retry()}>{t('Try again')}</Button>}
        />
      )}
      {advice && (
        <div className="rotation-stack" aria-busy={isUpdating}>
          <AdviceControls
            advice={advice}
            priorities={priorities}
            onCropChange={setCrop}
            onPriorityToggle={togglePriority}
          />
          <AdviceVerdict advice={advice} />
          <CropHistoryStrip advice={advice} />
          <CandidateList advice={advice} />
          <OffSeasonCard advice={advice} />
          {advice.dataGaps.length > 0 && (
            <Card>
              <InformationGaps
                title={t('What we do not know about this field')}
                gaps={advice.dataGaps}
              />
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
