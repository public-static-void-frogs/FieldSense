import { useSuspenseQuery } from '@tanstack/react-query';
import { Button, Card, Result, Skeleton } from 'antd';
import { ArrowLeft } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useLoaderData } from 'react-router-dom';
import { fieldQueries } from '../api/fields/fields.queries.ts';
import type { FieldRouteData } from '../app/route-loaders.ts';
import { CropIcon } from '../components/common/CropIcon';
import { PageHeading } from '../components/common/PageHeading';
import { RouterButton } from '../components/common/RouterButton';
import { FieldAssistant } from '../features/assistant/components/FieldAssistant';
import { InformationGaps } from '../features/rotation/components/InformationGaps';
import { OffSeasonCard } from '../features/rotation/components/OffSeasonCard';
import { RecommendationCalculator } from '../features/rotation/components/RecommendationCalculator';
import { useRotationAdvice } from '../features/rotation/hooks/useRotationAdvice.ts';
import { seasonYear } from '../features/rotation/utils/rotationPresentation.ts';
import '../styles/rotation.css';

export function FieldRecommendationPage() {
  const { t } = useTranslation();
  const { fieldId } = useLoaderData<FieldRouteData>();
  const { data: field } = useSuspenseQuery(fieldQueries.byId(fieldId));
  const {
    advice,
    isLoading,
    isUpdating,
    error,
    retry,
    selectedCrop,
    priorities,
    setCrop,
    togglePriority,
  } = useRotationAdvice(fieldId);
  if (!field) {
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
        title={
          <>
            {field.crop && (
              <>
                {field.crop} <span aria-hidden="true">·</span>{' '}
              </>
            )}
            {t('Crop recommendation')}
          </>
        }
        eyebrow=""
        actions={<FieldAssistant key={field.id} field={field} />}
        titlePrefix={
          <>
            <RouterButton
              type="text"
              icon={<ArrowLeft size={20} />}
              aria-label={t('Back to field')}
              to={`/fields/${field.id}`}
            />
            {field.crop && <CropIcon crop={field.crop} size={36} />}
          </>
        }
      />
      <div className="rotation-stack">
        {isLoading && (
          <Card>
            <Skeleton active paragraph={{ rows: 6 }} />
          </Card>
        )}
        {!advice && (error || advice === null) && (
          <Result
            status="warning"
            title={t('The recommendation could not be loaded')}
            extra={<Button onClick={() => retry()}>{t('Try again')}</Button>}
          />
        )}
        {advice && (
          <>
            <Card className="rotation-explainer">
              <h2>{t('How it works')}</h2>
              <p>
                {t(
                  'Compare crops for the {{year}} season using this field’s available crop history, soil data, and past weather. Choose the crop you plan to grow to see how it ranks, then select any goals you want the ranking to give more weight.',
                  { year: seasonYear(advice) },
                )}
              </p>
              <p>
                {t(
                  'Crops with lower scores rank higher. The leaderboard shows each crop’s risk level and estimated gross revenue where available. Open View details to see what contributed to the recommendation.',
                )}
              </p>
            </Card>
            <RecommendationCalculator
              advice={advice}
              selectedCrop={selectedCrop}
              priorities={priorities}
              isUpdating={isUpdating}
              onCropChange={setCrop}
              onPriorityToggle={togglePriority}
            />
            <div className="rotation-stack" aria-busy={isUpdating}>
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
          </>
        )}
      </div>
    </div>
  );
}
