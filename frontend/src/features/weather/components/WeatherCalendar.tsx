import { WeatherRiskIndicator } from './WeatherRiskIndicator';
import { WeatherConditionIcon } from './WeatherConditionIcon';
import type { CSSProperties } from 'react';
import { Droplet } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type {
  WeatherMetric,
  WeatherRecord,
  WeatherUnits,
} from '../../../types/weather/weather.types.ts';
import { formatWeatherValue, getWeatherMetricConfig } from '../utils/weatherPresentation.ts';
import { weatherColor } from '../utils/weatherVisuals.ts';

type WeatherCalendarProps = {
  records: WeatherRecord[];
  metric: WeatherMetric;
  units: WeatherUnits;
  selectedKey: number;
  onSelect: (key: number) => void;
};

export function WeatherCalendar({
  records,
  metric,
  units,
  selectedKey,
  onSelect,
}: WeatherCalendarProps) {
  const { t, i18n } = useTranslation();
  const config = getWeatherMetricConfig(metric, t, units);

  return (
    <div className="weather-calendar" role="group" aria-label={t('14-day conditions calendar')}>
      {records.map((record, index) => {
        const date = new Date(`${record.date}T12:00:00Z`);
        let dayLabel = new Intl.DateTimeFormat(i18n.resolvedLanguage, {
          weekday: 'short',
          timeZone: 'UTC',
        }).format(date);
        if (record.today) {
          dayLabel = t('Today');
        } else if (index === 1) {
          dayLabel = t('Tomorrow');
        }
        const color = weatherColor(record[metric], metric, units);
        let alertLabel = '';
        if (record.cropAssessment?.alerts.length) {
          const risk =
            record.cropAssessment.riskLevel === 'high' ? t('High crop risk') : t('Crop caution');
          alertLabel = `, ${risk}`;
        }
        let secondaryValue = formatWeatherValue(record.rainfall, units.rainfall);
        if (metric === 'rainfall') {
          secondaryValue = formatWeatherValue(record.rainChance, '%');
        }
        const dateLabel = new Intl.DateTimeFormat(i18n.resolvedLanguage, {
          month: 'short',
          day: 'numeric',
          timeZone: 'UTC',
        }).format(date);

        return (
          <button
            type="button"
            key={record.date}
            className="weather-calendar-day"
            data-selected={selectedKey === record.key}
            data-today={record.today}
            aria-pressed={selectedKey === record.key}
            aria-label={`${dateLabel}: ${t(record.conditions)}, ${config.title} ${formatWeatherValue(record[metric], config.unit)}${alertLabel}`}
            onClick={() => onSelect(record.key)}
            style={{ '--day-color': color } as CSSProperties}
          >
            <span className="weather-calendar-weekday">
              {dayLabel}
              <WeatherRiskIndicator assessment={record.cropAssessment} />
            </span>
            <span className="weather-calendar-date">{dateLabel}</span>
            <WeatherConditionIcon
              conditions={record.conditions}
              size={40}
              className="weather-calendar-icon"
            />
            <strong className="weather-calendar-value">
              {formatWeatherValue(record[metric])}
              <small>{config.unit}</small>
            </strong>
            <span className="weather-calendar-secondary">
              <Droplet size={12} fill="currentColor" strokeWidth={0} />
              {secondaryValue}
            </span>
            <span className="weather-calendar-color" />
          </button>
        );
      })}
    </div>
  );
}
