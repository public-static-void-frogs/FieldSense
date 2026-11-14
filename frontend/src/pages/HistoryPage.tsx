import type { HistoryRange } from '../api/weather/weather.api.ts';
import { WeatherConditionIcon } from '../features/weather/components/WeatherConditionIcon';
import { useWeatherHistoryBounds } from '../features/weather/hooks/useWeatherHistoryBounds.ts';
import { useQuery, useSuspenseQueries, useSuspenseQuery } from '@tanstack/react-query';
import type { TableColumnsType } from 'antd';
import { Card, DatePicker, Flex, Segmented, Select, Space, Table } from 'antd';
import { History } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { fieldQueries } from '../api/fields/fields.queries.ts';
import { farmQueries } from '../api/farm/farm.queries.ts';
import { weatherQueries } from '../api/weather/weather.queries.ts';
import { ForecastPanel } from '../features/weather/components/ForecastPanel';
import { HistoryChart } from '../features/weather/components/HistoryChart';
import { WeatherDayDetails } from '../features/weather/components/WeatherDayDetails';
import { WeatherMetricTabs } from '../features/weather/components/WeatherMetricTabs';
import { WeatherStatus } from '../features/weather/components/WeatherStatus';
import { historyRanges } from '../features/weather/constants/weather.constants.ts';
import { useCropWeatherField } from '../features/weather/hooks/useCropWeatherField.ts';
import { useWeatherSelection } from '../features/weather/hooks/useWeatherSelection.ts';
import {
  formatWeatherDate,
  formatWeatherValue,
  selectWeatherReading,
  windDirection,
} from '../features/weather/utils/weatherPresentation.ts';
import type {
  WeatherMetric,
  WeatherRecord,
  WeatherSeries,
} from '../types/weather/weather.types.ts';

export function HistoryPage() {
  const { t } = useTranslation();
  const [{ data: fields }, { data: supportedCrops }] = useSuspenseQueries({
    queries: [fieldQueries.list(), fieldQueries.crops()],
  });
  const { crop, cropOptions, field, matchingFields, selectCrop, selectField } = useCropWeatherField(
    fields,
    supportedCrops,
  );
  const [metric, setMetric] = useState<WeatherMetric>('temperature');

  return (
    <div className="environment-page">
      <div className="environment-sticky-header">
        <WeatherMetricTabs metric={metric} onChange={setMetric} />
        <div className="weather-assessment-toolbar">
          <Select
            id="weather-crop"
            aria-label={t('Crop for weather assessment')}
            value={crop?.value}
            onChange={selectCrop}
            disabled={!cropOptions.length}
            placeholder={t('No crops available')}
            options={cropOptions}
          />
          {matchingFields.length > 1 && (
            <Select
              id="weather-field"
              aria-label={t('Field for crop assessment')}
              value={field?.id}
              onChange={selectField}
              popupMatchSelectWidth={false}
              options={matchingFields.map((item) => {
                const [longitude, latitude] = item.geometry.coordinates;
                const location = `${latitude.toFixed(5)}, ${longitude.toFixed(5)}`;
                return {
                  value: item.id,
                  label: item.name === item.crop ? location : `${location} · ${item.name}`,
                };
              })}
            />
          )}
        </div>
      </div>
      {!crop && (
        <p className="weather-crop-note">
          {t('Add a field with a supported crop to see growing-season risk zones.')}
        </p>
      )}
      <ForecastPanel metric={metric} fieldId={field?.id} />
      <HistoricalWeather metric={metric} fieldId={field?.id} />
    </div>
  );
}

type HistoricalWeatherProps = { metric: WeatherMetric; fieldId?: string };

function HistoricalWeather({ metric, fieldId }: HistoricalWeatherProps) {
  const { t } = useTranslation();
  const { data: preferences } = useSuspenseQuery(farmQueries.profile());
  const { range, dates, period, changeRange, changeDates, selectedKey, selectReading } =
    useWeatherSelection();
  const query = useQuery(weatherQueries.history(preferences, period, fieldId));
  const series = query.data;
  const bounds = useWeatherHistoryBounds(series?.timeZone ?? preferences.timeZone);

  return (
    <section
      className="environment-past"
      aria-label={t('Past conditions')}
      aria-busy={query.isFetching}
    >
      <Card
        className="weather-history-card"
        title={
          <span className="weather-section-title">
            <History size={19} />
            {t('Past conditions')}
          </span>
        }
        extra={
          <Flex gap={10} wrap align="center">
            <Segmented<HistoryRange | 'custom'>
              aria-label={t('Weather history time range')}
              options={historyRanges.map((value) => ({ value, label: t(value) }))}
              value={dates ? 'custom' : range}
              onChange={(value) => {
                if (value !== 'custom') {
                  changeRange(value);
                }
              }}
            />
            <DatePicker.RangePicker
              aria-label={t('Historical date range')}
              value={dates}
              onChange={changeDates}
              maxDate={bounds.maxDate}
              minDate={bounds.minDate}
              disabledDate={(date, { from }) =>
                Boolean(from && Math.abs(date.diff(from, 'day')) > 365)
              }
            />
          </Flex>
        }
      >
        {series && series.records.length > 0 && !query.isError ? (
          <HistoryExplorer
            series={series}
            metric={metric}
            selectedKey={selectedKey}
            onSelect={selectReading}
            cropRequested={Boolean(fieldId)}
          />
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
    </section>
  );
}

type HistoryExplorerProps = {
  series: WeatherSeries;
  metric: WeatherMetric;
  selectedKey: number;
  onSelect: (key: number) => void;
  cropRequested: boolean;
};

function HistoryExplorer({
  series,
  metric,
  selectedKey,
  onSelect,
  cropRequested,
}: HistoryExplorerProps) {
  const { t } = useTranslation();
  const { records, units } = series;
  const selected = selectWeatherReading(records, selectedKey);

  return (
    <>
      <HistoryChart
        records={records}
        metric={metric}
        selectedKey={selected.key}
        onSelect={onSelect}
        units={units}
        assessment={series.cropAssessment}
        cropRequested={cropRequested}
      />
      <WeatherDayDetails
        record={selected}
        records={records}
        metric={metric}
        units={units}
        soilDepth={series.soilDepth}
        onSelect={onSelect}
      />
      <details className="weather-history-log">
        <summary>{t('Daily environment log')}</summary>
        <DailyLog series={series} selectedKey={selected.key} onSelect={onSelect} />
      </details>
    </>
  );
}

type DailyLogProps = {
  series: WeatherSeries;
  selectedKey: number;
  onSelect: (key: number) => void;
};

function DailyLog({ series, selectedKey, onSelect }: DailyLogProps) {
  const { t, i18n } = useTranslation();
  const { records, units } = series;
  const columns: TableColumnsType<WeatherRecord> = [
    {
      title: t('Date'),
      dataIndex: 'date',
      render: (value: string) => formatWeatherDate(value, i18n.resolvedLanguage),
    },
    {
      title: t('Conditions'),
      dataIndex: 'conditions',
      render: (value: string) => {
        return (
          <Space>
            <WeatherConditionIcon conditions={value} size={20} />
            {t(value)}
          </Space>
        );
      },
    },
    {
      title: t('High / low'),
      dataIndex: 'temperature',
      render: (value: number | null, record) =>
        `${formatWeatherValue(value)} / ${formatWeatherValue(record.low, units.temperature)}`,
    },
    {
      title: t('Precipitation'),
      dataIndex: 'rainfall',
      render: (value: number | null) => formatWeatherValue(value, units.rainfall),
    },
    {
      title: t('Humidity'),
      dataIndex: 'humidity',
      render: (value: number | null) => formatWeatherValue(value, '%'),
    },
    {
      title: t('Wind'),
      dataIndex: 'wind',
      render: (value: number | null, record) =>
        `${formatWeatherValue(value, units.wind)} ${windDirection(record.windDirection, t)}`,
    },
  ];

  return (
    <section className="weather-daily-log" aria-label={t('Daily environment log')}>
      <Table<WeatherRecord>
        rowKey="date"
        columns={columns}
        dataSource={records}
        scroll={{ x: 900 }}
        pagination={{ pageSize: 10, size: 'small', showSizeChanger: false }}
        rowClassName={(record) =>
          record.key === selectedKey ? 'environment-selected-row' : 'clickable-row'
        }
        onRow={(record) => ({ onClick: () => onSelect(record.key) })}
      />
    </section>
  );
}
