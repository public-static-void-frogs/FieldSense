import { Tabs } from 'antd';
import { useTranslation } from 'react-i18next';
import type { WeatherMetric } from '../../../types/weather/weather.types.ts';
import { weatherMetrics } from '../constants/weather.constants.ts';
import { getWeatherMetricIcon } from '../utils/weatherPresentation.ts';

type WeatherMetricTabsProps = { metric: WeatherMetric; onChange: (metric: WeatherMetric) => void };

export function WeatherMetricTabs({ metric, onChange }: WeatherMetricTabsProps) {
  const { t } = useTranslation();

  return (
    <Tabs
      className="fields-view-tabs environment-tabs"
      activeKey={metric}
      onChange={(key) => onChange(key as WeatherMetric)}
      items={Object.entries(weatherMetrics).map(([key, item]) => {
        const Icon = getWeatherMetricIcon(key as WeatherMetric);

        return {
          key,
          label: (
            <span className="environment-tab-label">
              <Icon size={17} />
              {t(item.title)}
            </span>
          ),
        };
      })}
    />
  );
}
