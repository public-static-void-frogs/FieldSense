import { formatCropAlert } from '../utils/cropRiskPresentation.ts';
import { WeatherConditionIcon } from './WeatherConditionIcon';
import { useTranslation } from 'react-i18next';
import type {
  WeatherMetric,
  WeatherRecord,
  WeatherUnits,
} from '../../../types/weather/weather.types.ts';
import {
  formatWeatherDate,
  formatWeatherValue,
  getWeatherMetricConfig,
} from '../utils/weatherPresentation.ts';

type WeatherChartTooltipProps = {
  active?: boolean;
  payload?: ReadonlyArray<{ payload?: WeatherRecord }>;
  metric: WeatherMetric;
  units: WeatherUnits;
};

export function WeatherChartTooltip({ active, payload, metric, units }: WeatherChartTooltipProps) {
  const { t, i18n } = useTranslation();
  const record = payload?.[0]?.payload;
  if (!active || !record) {
    return null;
  }
  const config = getWeatherMetricConfig(metric, t, units);

  return (
    <div className="weather-chart-tooltip">
      <span>{formatWeatherDate(record.date, i18n.resolvedLanguage)}</span>
      <div>
        <WeatherConditionIcon conditions={record.conditions} size={24} />
        <strong>{formatWeatherValue(record[metric], config.unit)}</strong>
      </div>
      <span>
        {config.title} · {t(record.conditions)}
      </span>
      <small>
        {t('High / low')} {formatWeatherValue(record.temperature)} /{' '}
        {formatWeatherValue(record.low, units.temperature)}
      </small>
      <small>
        {t('Precipitation')} {formatWeatherValue(record.rainfall, units.rainfall)}
      </small>
      {record.cropAssessment?.suitabilityScore != null && (
        <small>
          {t('Suitability {{score}} / 100', {
            score: formatWeatherValue(record.cropAssessment.suitabilityScore),
          })}
        </small>
      )}
      {record.cropAssessment?.alerts
        .filter((alert) => alert.metric === metric)
        .map((alert) => (
          <small key={`${alert.metric}-${alert.reading}`}>
            ⚠️ {formatCropAlert(alert, units, t, i18n.resolvedLanguage)}
          </small>
        ))}
    </div>
  );
}
