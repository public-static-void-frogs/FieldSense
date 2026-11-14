import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Collapse, DatePicker, Segmented, Spin, Table, Tabs } from 'antd';
import dayjs from 'dayjs';
import { Droplets } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  soilMoistureQueries,
  type SoilMoistureLocation,
} from '../../../api/fields/soil-moisture.queries.ts';
import type {
  MoistureFrequency,
  MoistureStats,
  MoisturePeriod,
  MoistureSource,
  CurrentSoilMoisture,
} from '../../../types/fields/soil-moisture.types.ts';
import { SoilDataView } from './SoilDataView';
import './FieldInsights.css';

const sourceNames = { openmeteo: 'Open-Meteo · ERA5-Land', power: 'NASA POWER' };
const statisticKeys = ['n', 'mean', 'min', 'max', 'p10', 'p50', 'p90'] as const;
const statisticLabels = {
  n: 'Readings',
  mean: 'Mean',
  min: 'Minimum',
  max: 'Maximum',
  p10: 'P10',
  p50: 'P50',
  p90: 'P90',
} as const;

function moistureNumber(value: number | null | undefined, locale: string) {
  if (value == null) {
    return '—';
  }
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 4 }).format(value);
}

function useMoistureLabels() {
  const { t } = useTranslation();

  return (key: string, current = false) => {
    if (key === 'profile_mean') {
      return current ? t('Profile mean (0–81 cm)') : t('Profile mean (0–100 cm)');
    }
    if (key === 'GWETTOP') {
      return t('Surface wetness');
    }
    if (key === 'GWETROOT') {
      return t('Root-zone wetness');
    }
    if (key === 'GWETPROF') {
      return t('Full-profile wetness');
    }
    const depth = /^soil_moisture_(\d+)_to_(\d+)cm$/.exec(key);
    if (depth) {
      return t('{{top}}–{{bottom}} cm', { top: depth[1], bottom: depth[2] });
    }
    return key;
  };
}

export function FieldSoilMoisture(location: SoilMoistureLocation) {
  const { t } = useTranslation();

  return (
    <Collapse
      className="field-insights-soil"
      destroyOnHidden
      items={[
        {
          key: 'moisture',
          label: t('Soil moisture'),
          extra: <Droplets size={17} aria-hidden />,
          children: (
            <div className="field-insights-panel">
              <Tabs
                destroyOnHidden
                items={[
                  {
                    key: 'current',
                    label: t('Current readings'),
                    children: <CurrentMoisture {...location} />,
                  },
                  {
                    key: 'history',
                    label: t('Historical readings'),
                    children: <MoistureHistory {...location} />,
                  },
                  {
                    key: 'comparison',
                    label: t('Seasonal comparison'),
                    children: <MoistureComparison {...location} />,
                  },
                ]}
              />
            </div>
          ),
        },
      ]}
    />
  );
}

function MoistureError({ retry }: { retry: () => void }) {
  const { t } = useTranslation();

  return (
    <Alert
      type="error"
      title={t('Could not load soil moisture.')}
      action={<Button onClick={retry}>{t('Retry')}</Button>}
    />
  );
}

function CurrentMoisture(location: SoilMoistureLocation) {
  const query = useQuery(soilMoistureQueries.current(location));

  if (query.isError) {
    return <MoistureError retry={() => void query.refetch()} />;
  }
  if (!query.data) {
    return <Spin />;
  }

  return <CurrentReadings data={query.data} />;
}

function CurrentReadings({ data }: { data: CurrentSoilMoisture }) {
  const { t, i18n } = useTranslation();
  const label = useMoistureLabels();
  if (!data.time_utc) {
    return <Alert type="info" title={t('No modeled readings are available for this point.')} />;
  }
  const time = new Intl.DateTimeFormat(i18n.language, {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'UTC',
  }).format(new Date(data.time_utc));
  const rows = Object.entries({ ...data.layers, profile_mean: data.profile_mean });

  return (
    <SoilDataView
      title={t('Current readings')}
      help={`Open-Meteo · ${time} UTC · m³/m³`}
      unit="m³/m³"
      rows={rows.map(([key, value]) => ({ label: label(key, true), values: { moisture: value } }))}
      series={[{ key: 'moisture', label: t('Soil moisture') }]}
    >
      <Table
        size="small"
        pagination={false}
        rowKey={([key]) => key}
        dataSource={rows}
        columns={[
          { title: t('Soil layer'), render: (_, [key]) => label(key, true) },
          {
            title: t('Soil moisture'),
            align: 'right',
            render: (_, [, value]) => moistureNumber(value, i18n.language),
          },
        ]}
      />
    </SoilDataView>
  );
}

function initialPeriod(): MoisturePeriod {
  const end = dayjs().subtract(7, 'day');

  return {
    source: 'openmeteo',
    frequency: 'daily',
    start: end.subtract(29, 'day').format('YYYY-MM-DD'),
    end: end.format('YYYY-MM-DD'),
  };
}

function MoistureHistory(location: SoilMoistureLocation) {
  const { t, i18n } = useTranslation();
  const label = useMoistureLabels();
  const [period, setPeriod] = useState(initialPeriod);
  const query = useQuery(soilMoistureQueries.history(location, period));
  const rows = query.data?.series ?? [];
  const keys = Object.keys(rows[0]?.values ?? {});
  const stats = Object.entries(query.data?.stats ?? {});
  const format = (value: number | null | undefined) => moistureNumber(value, i18n.language);
  const endLimit = dayjs().subtract(7, 'day').endOf('day');
  const earliest = dayjs(period.source === 'power' ? '1981-01-01' : '1950-01-01');
  const maxDays = period.frequency === 'hourly' ? 31 : 366;
  const unit = period.source === 'power' ? t('Fraction of saturation (0–1)') : 'm³/m³';

  return (
    <div className="field-insights-panel">
      <div className="field-soil-moisture-controls">
        <Segmented<MoistureSource>
          aria-label={t('Soil moisture source')}
          value={period.source}
          options={Object.entries(sourceNames).map(([value, label]) => ({
            value: value as MoistureSource,
            label,
          }))}
          onChange={(source) => {
            const next = { ...period, source, frequency: 'daily' as const };
            if (source === 'power' && next.start < '1981-01-01') {
              setPeriod({ ...initialPeriod(), source });
            } else {
              setPeriod(next);
            }
          }}
        />
        {period.source === 'openmeteo' && (
          <Segmented<MoistureFrequency>
            aria-label={t('Reading interval')}
            value={period.frequency}
            options={[
              { value: 'daily', label: t('Daily') },
              { value: 'hourly', label: t('Hourly') },
            ]}
            onChange={(frequency) => {
              const hourlyStart = dayjs(period.end).subtract(30, 'day').format('YYYY-MM-DD');

              setPeriod({
                ...period,
                frequency,
                start:
                  frequency === 'hourly' && period.start < hourlyStart ? hourlyStart : period.start,
              });
            }}
          />
        )}
        <DatePicker.RangePicker
          aria-label={t('Soil moisture date range')}
          allowClear={false}
          value={[dayjs(period.start), dayjs(period.end)]}
          disabledDate={(value, { from }) =>
            value.isBefore(earliest, 'day') ||
            value.isAfter(endLimit, 'day') ||
            Boolean(from && Math.abs(value.diff(from, 'day')) >= maxDays)
          }
          onChange={(dates) => {
            if (dates?.[0] && dates[1]) {
              setPeriod({
                ...period,
                start: dates[0].format('YYYY-MM-DD'),
                end: dates[1].format('YYYY-MM-DD'),
              });
            }
          }}
        />
      </div>
      <small>
        {unit} · UTC · {t('Archives may lag by several days.')}
      </small>
      {query.isError && <MoistureError retry={() => void query.refetch()} />}
      {query.isPending && <Spin />}
      {query.data && rows.length === 0 && (
        <Alert type="info" title={t('No soil moisture readings in this range.')} />
      )}
      {rows.length > 0 && (
        <>
          <SoilDataView
            title={t('Layer statistics')}
            unit={unit}
            rows={stats.map(([key, values]) => ({ label: label(key), values }))}
            series={statisticKeys.map((key) => ({
              key,
              label: t(statisticLabels[key]),
              count: key === 'n',
            }))}
          >
            <Table
              size="small"
              pagination={false}
              scroll={{ x: true }}
              rowKey={([key]) => key}
              dataSource={stats}
              columns={[
                { title: t('Soil layer'), render: (_, [key]) => label(key) },
                ...statisticKeys.map((key) => ({
                  title: t(statisticLabels[key]),
                  align: 'right' as const,
                  render: (_: unknown, [, stats]: [string, MoistureStats]) => format(stats[key]),
                })),
              ]}
            />
          </SoilDataView>
          <SoilDataView
            title={t('Historical readings')}
            kind="line"
            unit={unit}
            rows={rows.map((row) => ({
              label: row.time_utc?.slice(0, 16).replace('T', ' ') ?? row.date,
              values: row.values,
            }))}
            series={keys.map((key) => ({ key, label: label(key) }))}
          >
            <Table
              size="small"
              scroll={{ x: true }}
              rowKey={(row) => row.time_utc ?? row.date}
              pagination={{ defaultPageSize: 10, hideOnSinglePage: true }}
              dataSource={rows}
              columns={[
                {
                  title: t('Date'),
                  render: (_, row) => row.time_utc?.slice(0, 16).replace('T', ' ') ?? row.date,
                },
                ...keys.map((key) => ({
                  title: label(key),
                  align: 'right' as const,
                  render: (_: unknown, row: (typeof rows)[number]) => format(row.values[key]),
                })),
              ]}
            />
          </SoilDataView>
        </>
      )}
    </div>
  );
}

function MoistureComparison(location: SoilMoistureLocation) {
  const { t, i18n } = useTranslation();
  const query = useQuery(soilMoistureQueries.comparison(location));
  if (query.isError) {
    return <MoistureError retry={() => void query.refetch()} />;
  }
  if (!query.data) {
    return <Spin />;
  }
  const { current, past_mean, anomaly, percentile, years, window_days, unavailable_years } =
    query.data;
  const format = (value: number | null) => moistureNumber(value, i18n.language);
  const metrics = [
    { label: t('Profile mean (0–81 cm)'), value: format(current.profile_mean) },
    { label: t('Historical mean (0–100 cm)'), value: format(past_mean) },
    { label: t('Difference from historical mean'), value: format(anomaly) },
    { label: t('Historical percentile'), value: percentile == null ? '—' : format(percentile) },
  ];

  return (
    <div className="field-insights-panel">
      <div className="field-insights-panel">
        {current.profile_mean == null && (
          <Alert type="info" title={t('No complete current profile is available.')} />
        )}
        {current.profile_mean != null && past_mean == null && (
          <Alert
            type="info"
            title={t('At least three historical years are needed for comparison.')}
          />
        )}
        <dl className="field-soil-moisture-comparison">
          {metrics.map(({ label, value }) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
        <small>Open-Meteo · ERA5-Land · m³/m³</small>
      </div>
      <SoilDataView
        title={t('Seasonal comparison')}
        help={t(
          'The current 0–81 cm profile is compared with the archive’s 0–100 cm profile for the same time of year (the date and preceding {{days}} days).',
          { days: window_days },
        )}
        unit="m³/m³"
        rows={Object.entries(years).map(([year, value]) => ({
          label: year,
          values: { moisture: value },
        }))}
        series={[{ key: 'moisture', label: t('Profile mean (0–100 cm)') }]}
      >
        {Object.keys(years).length > 0 && (
          <Table
            size="small"
            pagination={false}
            rowKey={([year]) => year}
            dataSource={Object.entries(years).reverse()}
            columns={[
              { title: t('Year'), render: (_, [year]) => year },
              {
                title: t('Profile mean (0–100 cm)'),
                align: 'right',
                render: (_, [, value]) => format(value),
              },
            ]}
          />
        )}
      </SoilDataView>
      {unavailable_years.length > 0 && (
        <small>
          {t('Years without usable readings')} · {unavailable_years.join(', ')}
        </small>
      )}
    </div>
  );
}
