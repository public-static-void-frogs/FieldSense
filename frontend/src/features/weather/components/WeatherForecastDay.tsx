import { Card, Descriptions, Space, Statistic, Typography } from 'antd';
import { CalendarDays } from 'lucide-react';
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
  windDirection,
} from '../utils/weatherPresentation.ts';
import { WeatherConditionIcon } from './WeatherConditionIcon';
import { WeatherDayInsight } from './WeatherDayInsight';
import { WeatherRiskIndicator } from './WeatherRiskIndicator';
import { WeatherScene } from './WeatherScene';

type WeatherForecastDayProps = {
  record: WeatherRecord;
  metric: WeatherMetric;
  units: WeatherUnits;
  soilDepth: string;
  fieldId?: string;
};

export function WeatherForecastDay({
  record,
  metric,
  units,
  soilDepth,
  fieldId,
}: WeatherForecastDayProps) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? 'en';
  const config = getWeatherMetricConfig(metric, t, units);

  return (
    <section
      className="weather-selected-day"
      aria-label={t('Selected day conditions')}
      aria-live="polite"
    >
      <Card
        className="weather-conditions-card"
        extra={<WeatherRiskIndicator assessment={record.cropAssessment} />}
        title={
          <Space>
            <CalendarDays size={19} />
            {formatWeatherDate(record.date, i18n.resolvedLanguage)}
          </Space>
        }
      >
        <WeatherScene key={record.conditions} conditions={record.conditions} />
        <div className="weather-forecast-hero">
          <Statistic
            title={config.title}
            value={record[metric] ?? '—'}
            formatter={() => formatWeatherValue(record[metric])}
            suffix={record[metric] === null ? undefined : config.unit}
          />
          <div className="weather-forecast-condition">
            <WeatherConditionIcon conditions={record.conditions} size={72} />
            <Typography.Text type="secondary">{t(record.conditions)}</Typography.Text>
          </div>
        </div>
        <Descriptions
          className="weather-day-readings"
          size="small"
          layout="vertical"
          column={{ xs: 1, sm: 2, xl: 3 }}
          colon={false}
          items={[
            {
              key: 'temperature',
              label: t('High / low'),
              children: `${formatWeatherValue(record.temperature)} / ${formatWeatherValue(record.low, units.temperature)}`,
            },
            {
              key: 'rainfall',
              label: t('Precipitation'),
              children: formatWeatherValue(record.rainfall, units.rainfall),
            },
            {
              key: 'moisture',
              label: (
                <span>
                  {t('Soil moisture')} · {soilDepth}
                </span>
              ),
              children: formatWeatherValue(record.moisture, '%'),
            },
            {
              key: 'humidity',
              label: t('Humidity'),
              children: formatWeatherValue(record.humidity, '%'),
            },
            {
              key: 'wind',
              label: t('Wind'),
              children: `${formatWeatherValue(record.wind, units.wind)} ${windDirection(record.windDirection, t)}`,
            },
            {
              key: 'rainChance',
              label: t('Rain chance'),
              children: formatWeatherValue(record.rainChance, '%'),
            },
          ]}
        />
      </Card>
      <WeatherDayInsight
        key={JSON.stringify([fieldId, record.date, locale])}
        locale={locale}
        record={record}
        units={units}
        fieldId={fieldId}
      />
    </section>
  );
}
