import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, theme } from 'antd';
import { Info } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { rotationMutations } from '../../../api/rotation/rotation.mutations.ts';
import { rotationQueries } from '../../../api/rotation/rotation.queries.ts';
import './CustomMetricsBanner.css';

type CustomMetricsBannerProps = {
  fieldId: string;
  onView?: () => void;
  onClear: () => void;
};

export function CustomMetricsBanner({ fieldId, onView, onClear }: CustomMetricsBannerProps) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const client = useQueryClient();
  const { data: seasons } = useQuery(rotationQueries.seasonResults(fieldId));
  const { data: survey } = useQuery(rotationQueries.soilSurvey(fieldId));
  const { data: economics } = useQuery(rotationQueries.economics(fieldId));
  const reset = useMutation(rotationMutations.resetInputs(client, fieldId));
  const inputs = economics?.inputs;
  const hasCustomMetrics =
    Boolean(seasons?.results.length) ||
    Boolean(survey) ||
    typeof inputs?.landRentUsdPerAcre === 'number' ||
    inputs?.crops.some(
      ({ priceUsd, costUsdPerAcre }) =>
        typeof priceUsd === 'number' || typeof costUsdPerAcre === 'number',
    );

  if (!hasCustomMetrics) {
    return null;
  }

  return (
    <div
      className="rotation-metrics-banner"
      style={{ backgroundColor: token.colorPrimary, color: token.colorTextLightSolid }}
    >
      <div className="rotation-metrics-banner-message" role="status">
        <Info size={15} aria-hidden="true" />
        <span>
          {t('Custom metrics are applied')}
          {reset.isError && <> {t('Custom metrics could not be cleared. Please try again.')}</>}
        </span>
      </div>
      <div className="rotation-metrics-banner-actions">
        <Button ghost size="small" disabled={!onView} onClick={onView}>
          {t('View')}
        </Button>
        <Button
          ghost
          size="small"
          loading={reset.isPending}
          onClick={() => reset.mutate(fieldId, { onSuccess: onClear })}
        >
          {t('Clear')}
        </Button>
      </div>
    </div>
  );
}
