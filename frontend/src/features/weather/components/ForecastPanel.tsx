import { useQuery, useSuspenseQuery } from '@tanstack/react-query';
import { Card } from 'antd';
import { useState } from 'react';
import { farmQueries } from '../../../api/farm/farm.queries.ts';
import { weatherQueries } from '../../../api/weather/weather.queries.ts';
import type { WeatherMetric, WeatherSeries } from '../../../types/weather/weather.types.ts';
import { selectWeatherReading } from '../utils/weatherPresentation.ts';
import { HistoryChart } from './HistoryChart';
import { WeatherCalendar } from './WeatherCalendar';
import { WeatherForecastDay } from './WeatherForecastDay';
import { WeatherMetricTabs } from './WeatherMetricTabs';
import { WeatherStatus } from './WeatherStatus';

type ForecastPanelProps = { metric?: WeatherMetric; fieldId?: string };

export function ForecastPanel({ metric, fieldId }: ForecastPanelProps) {
  const { data: preferences } = useSuspenseQuery(farmQueries.profile());
  const query = useQuery(weatherQueries.forecast(preferences, fieldId));
  const [localMetric, setMetric] = useState<WeatherMetric>('temperature');
  const activeMetric = metric ?? localMetric;

  return (
    <>
      {!metric && <WeatherMetricTabs metric={localMetric} onChange={setMetric} />}
      <Card className="weather-forecast-card">
        {query.data && query.data.records.length > 0 && !query.isError ? (
          <ForecastExplorer data={query.data} metric={activeMetric} fieldId={fieldId} />
        ) : (
          <WeatherStatus
            hasLocation={
              Boolean(fieldId) || (preferences.latitude !== null && preferences.longitude !== null)
            }
            pending={query.isLoading}
            error={query.error}
            retry={() => void query.refetch()}
          />
        )}
      </Card>
    </>
  );
}

type ForecastExplorerProps = { data: WeatherSeries; metric: WeatherMetric; fieldId?: string };

function ForecastExplorer({ data, metric, fieldId }: ForecastExplorerProps) {
  const [selectedKey, selectReading] = useState(0);
  const selected = selectWeatherReading(data.records, selectedKey);

  return (
    <>
      <div className="weather-forecast-stack">
        <div className="weather-forecast-calendar">
          <WeatherCalendar
            records={data.records}
            units={data.units}
            metric={metric}
            selectedKey={selected.key}
            onSelect={selectReading}
          />
        </div>
        <WeatherForecastDay
          record={selected}
          units={data.units}
          metric={metric}
          soilDepth={data.soilDepth}
          fieldId={fieldId}
        />
        <div className="weather-forecast-trend">
          <HistoryChart
            records={data.records}
            units={data.units}
            metric={metric}
            selectedKey={selected.key}
            onSelect={selectReading}
            forecast
            assessment={data.cropAssessment}
            cropRequested={Boolean(fieldId)}
          />
        </div>
      </div>
    </>
  );
}
