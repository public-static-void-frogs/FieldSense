import { WeatherConditionIcon } from './WeatherConditionIcon';
import { useQuery, useSuspenseQuery } from '@tanstack/react-query';
import { Card, Divider, Flex, Space, Statistic, Typography } from 'antd';
import { ArrowRight, CloudRain, Droplets, MapPin, Wind } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { farmQueries } from '../../../api/farm/farm.queries.ts';
import { weatherQueries } from '../../../api/weather/weather.queries.ts';
import { RouterButton } from '../../../components/common/RouterButton';
import {
  formatWeatherDate,
  formatWeatherValue,
  windDirection,
} from '../utils/weatherPresentation.ts';
import { WeatherSource } from './WeatherSource';
import { WeatherStatus } from './WeatherStatus';

export function WeatherCard() {
  const { t, i18n } = useTranslation();
  const { data: preferences } = useSuspenseQuery(farmQueries.profile());
  const query = useQuery(weatherQueries.current(preferences));
  const weather = query.data;

  if (!weather || query.isError) {
    return (
      <Card className="weather-card" title={t('Weather today')}>
        <WeatherStatus
          hasLocation={preferences.latitude !== null && preferences.longitude !== null}
          pending={query.isLoading}
          error={query.error}
          retry={() => void query.refetch()}
        />
      </Card>
    );
  }

  return (
    <Card
      className="weather-card"
      title={t('Weather today')}
      extra={
        <Space className="location-text">
          <MapPin size={16} />
          {weather.location}
        </Space>
      }
    >
      <Flex align="center" justify="space-between" gap={16}>
        <div>
          <Statistic
            value={weather.temperature ?? '—'}
            suffix={weather.units.temperature}
            precision={1}
          />
          <Typography.Paragraph>{t(weather.conditions)}</Typography.Paragraph>
          <Typography.Text type="secondary">
            {t('Feels like {{feelsLike}} · H {{high}} / L {{low}}', {
              feelsLike: formatWeatherValue(weather.feelsLike, weather.units.temperature),
              high: formatWeatherValue(weather.high, weather.units.temperature),
              low: formatWeatherValue(weather.low, weather.units.temperature),
            })}
          </Typography.Text>
        </div>
        <WeatherConditionIcon
          conditions={weather.conditions}
          size={72}
          strokeWidth={1.2}
          className="sun-icon"
        />
      </Flex>
      <Divider />
      <div className="weather-metrics">
        <div>
          <Droplets size={19} />
          <strong>{formatWeatherValue(weather.humidity, '%')}</strong>
          <Typography.Text type="secondary">{t('Humidity')}</Typography.Text>
        </div>
        <div>
          <Wind size={19} />
          <strong>{formatWeatherValue(weather.wind, weather.units.wind)}</strong>
          <Typography.Text type="secondary">
            {t('Wind')} · {windDirection(weather.windDirection, t)}
          </Typography.Text>
        </div>
        <div>
          <CloudRain size={19} />
          <strong>{formatWeatherValue(weather.rainChance, '%')}</strong>
          <Typography.Text type="secondary">{t('Rain chance')}</Typography.Text>
        </div>
      </div>
      <Divider />
      <div className="forecast">
        {weather.forecast.map((record) => {
          return (
            <div key={record.date}>
              <Typography.Text type="secondary">
                {formatWeatherDate(record.date, i18n.resolvedLanguage)}
              </Typography.Text>
              <WeatherConditionIcon
                conditions={record.conditions}
                size={27}
                aria-label={t(record.conditions)}
              />
              <strong>{formatWeatherValue(record.temperature, weather.units.temperature)}</strong>
            </div>
          );
        })}
      </div>
      <WeatherSource data={weather} />
      <RouterButton type="link" className="card-link" to="/history">
        {t('View weather history')} <ArrowRight size={18} />
      </RouterButton>
    </Card>
  );
}
