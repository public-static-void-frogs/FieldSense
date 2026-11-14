import { Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import type { CropDayAssessment } from '../../../types/weather/weather.types.ts';

type WeatherRiskIndicatorProps = { assessment?: CropDayAssessment | null };

export function WeatherRiskIndicator({ assessment }: WeatherRiskIndicatorProps) {
  const { t } = useTranslation();
  if (!assessment?.alerts.length) {
    return null;
  }
  const label = assessment.riskLevel === 'high' ? t('High crop risk') : t('Crop caution');

  return (
    <Tooltip
      title={t('{{risk}} · {{count}} alerts', { risk: label, count: assessment.alerts.length })}
    >
      <span
        className="weather-risk-indicator"
        data-risk={assessment.riskLevel}
        role="img"
        aria-label={label}
      >
        ⚠️
      </span>
    </Tooltip>
  );
}
