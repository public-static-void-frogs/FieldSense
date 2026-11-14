import { useQuery, useSuspenseQuery } from '@tanstack/react-query';
import { Alert, Card, Space, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { farmQueries } from '../../../api/farm/farm.queries.ts';
import { weatherQueries } from '../../../api/weather/weather.queries.ts';
import { weatherAdvisories } from '../utils/weatherAdvisories.ts';
import { formatWeatherDate } from '../utils/weatherPresentation.ts';
import { WeatherSource } from './WeatherSource';
import { WeatherStatus } from './WeatherStatus';

export function WeatherAdvisories() {
  const { t, i18n } = useTranslation();
  const { data: preferences } = useSuspenseQuery(farmQueries.profile());
  const query = useQuery(weatherQueries.forecast(preferences));

  if (!query.data || query.isError) {
    return (
      <Card title={t('Weather outlook')}>
        <WeatherStatus
          hasLocation={preferences.latitude !== null && preferences.longitude !== null}
          pending={query.isLoading}
          error={query.error}
          retry={() => void query.refetch()}
        />
      </Card>
    );
  }
  const messages = weatherAdvisories(query.data);

  return (
    <Card title={t('Weather outlook')}>
      <Space orientation="vertical" className="full-width">
        <Typography.Text type="secondary">
          {t('Next three days · model-based outlook, not official weather alerts.')}
        </Typography.Text>
        {messages.map(({ date, message }) => (
          <Alert
            key={`${date}-${message}`}
            type="info"
            showIcon
            title={`${formatWeatherDate(date, i18n.resolvedLanguage)} · ${t(message)}`}
          />
        ))}
        {messages.length === 0 && (
          <Typography.Text>
            {t('No outlook signals in the available data. Missing values are not assessed.')}
          </Typography.Text>
        )}
        <WeatherSource data={query.data} />
      </Space>
    </Card>
  );
}
