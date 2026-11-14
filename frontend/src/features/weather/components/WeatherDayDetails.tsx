import { Button, Select } from 'antd';
import { CheckCircle2, ChevronLeft, ChevronRight, CircleHelp, TriangleAlert } from 'lucide-react';
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
import { WeatherCropAlert } from './WeatherCropAlert';

const statusIcons = {
  good: CheckCircle2,
  caution: TriangleAlert,
  high: TriangleAlert,
  unknown: CircleHelp,
};

type WeatherDayDetailsProps = {
  record: WeatherRecord;
  records: WeatherRecord[];
  metric: WeatherMetric;
  units: WeatherUnits;
  soilDepth: string;
  onSelect: (key: number) => void;
};

export function WeatherDayDetails({
  record,
  records,
  metric,
  units,
  soilDepth,
  onSelect,
}: WeatherDayDetailsProps) {
  const { t, i18n } = useTranslation();
  const config = getWeatherMetricConfig(metric, t, units);
  const assessment = record.cropAssessment?.metrics[metric];
  const alerts = record.cropAssessment?.alerts.filter((alert) => alert.metric === metric) ?? [];
  const labels = {
    good: 'Good for crop',
    caution: 'Crop caution',
    high: 'High crop risk',
    unknown: 'Incomplete assessment',
  };
  const risk = assessment?.riskLevel ?? 'unknown';
  const missingReading =
    record[metric] === null || (metric === 'temperature' && record.low === null);
  const index = records.findIndex((item) => item.key === record.key);
  const previous = records[index + 1];
  const next = records[index - 1];
  const StatusIcon = statusIcons[risk];

  return (
    <section
      className="weather-history-reading"
      aria-label={t('Selected day conditions')}
      aria-live="polite"
    >
      <div className="weather-history-inspector-row">
        <div className="weather-history-day-navigation">
          <Button
            type="text"
            icon={<ChevronLeft size={20} />}
            aria-label={t('Previous day')}
            disabled={!previous}
            onClick={() => {
              if (previous) {
                onSelect(previous.key);
              }
            }}
          />
          <Select
            id="weather-history-day"
            variant="borderless"
            aria-label={t('Inspect weather date')}
            value={record.key}
            onChange={onSelect}
            options={records.map((item) => ({
              value: item.key,
              label: formatWeatherDate(item.date, i18n.resolvedLanguage),
            }))}
          />
          <Button
            type="text"
            icon={<ChevronRight size={20} />}
            aria-label={t('Next day')}
            disabled={!next}
            onClick={() => {
              if (next) {
                onSelect(next.key);
              }
            }}
          />
        </div>
        <div className="weather-history-measurement">
          <strong>
            {formatWeatherValue(record[metric])}
            <span>{config.unit}</span>
          </strong>
          <div className="weather-history-measurement-description">
            <span>{config.title}</span>
            {metric === 'temperature' && (
              <span>
                {t('Daily low')} {formatWeatherValue(record.low, config.unit)}
              </span>
            )}
            {metric === 'moisture' && <span>{soilDepth}</span>}
          </div>
        </div>
        {assessment && (
          <div className="weather-history-condition" data-risk={risk}>
            <StatusIcon size={21} aria-hidden="true" />
            <strong>{t(labels[risk])}</strong>
          </div>
        )}
      </div>
      {assessment && (alerts.length > 0 || missingReading) && (
        <div className="weather-history-alerts" data-risk={risk}>
          {alerts.length > 0 && (
            <ul>
              {alerts.map((alert) => (
                <WeatherCropAlert
                  key={`${alert.metric}-${alert.reading}`}
                  alert={alert}
                  units={units}
                />
              ))}
            </ul>
          )}
          {missingReading && <p>{t('Missing readings are not assessed.')}</p>}
        </div>
      )}
    </section>
  );
}
