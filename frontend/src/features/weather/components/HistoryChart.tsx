import './weather.css';
import { useTranslation } from 'react-i18next';
import {
  CartesianGrid,
  ComposedChart,
  LabelList,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type {
  CropAssessment,
  WeatherMetric,
  WeatherRecord,
  WeatherUnits,
} from '../../../types/weather/weather.types.ts';
import {
  cropChartDomain,
  cropRiskColors,
  weatherDayBounds,
  weatherReadingRisk,
} from '../utils/cropRiskPresentation.ts';
import { formatWeatherValue } from '../utils/weatherPresentation.ts';
import { useHistoryChart } from '../hooks/useHistoryChart.ts';
import { WeatherChartTooltip } from './WeatherChartTooltip';
import { WeatherBoundaryLabel, WeatherValueDot, WeatherValueLabel } from './WeatherChartMarks';
import { WeatherRiskBackground } from './WeatherRiskBackground';

type HistoryChartProps = {
  records: WeatherRecord[];
  metric: WeatherMetric;
  selectedKey: number;
  onSelect: (key: number) => void;
  units: WeatherUnits;
  forecast?: boolean;
  assessment?: CropAssessment | null;
  cropRequested?: boolean;
};

export function HistoryChart({
  records,
  metric,
  selectedKey,
  onSelect,
  units,
  forecast = false,
  assessment,
  cropRequested,
}: HistoryChartProps) {
  const { t, i18n } = useTranslation();
  const { gradientId, animate, config, timeline, selected, selectPoint } = useHistoryChart({
    records,
    metric,
    selectedKey,
    onSelect,
    units,
    forecast,
  });
  const bounds = assessment?.bounds[metric];
  const [minimum, maximum] = cropChartDomain(records, metric, bounds);
  const strokeId = `${gradientId}-risk`;
  const lowStrokeId = `${gradientId}-low-risk`;
  const today = records.find((record) => record.today);
  const unit = config.unit;
  const labelSpacing = metric === 'wind' ? 90 : 76;
  const chartWidth = Math.max(640, Math.min(14, records.length) * labelSpacing + 130);
  function dateLabel(value: string) {
    const record = records.find((item) => item.date === value);
    if (record?.today) {
      return t('Today');
    }
    return new Intl.DateTimeFormat(i18n.resolvedLanguage, {
      month: 'short',
      day: 'numeric',
      timeZone: 'UTC',
    }).format(new Date(`${value}T12:00:00Z`));
  }

  return (
    <div
      className={`weather-trend-chart weather-risk-chart ${forecast ? 'weather-chart-forecast' : 'weather-chart-history'}`}
    >
      {assessment && <CropRiskLegend assessment={assessment} />}
      {cropRequested && !assessment && (
        <p className="weather-crop-note">{t('Crop risk limits are unavailable for this field.')}</p>
      )}
      <div className="weather-risk-scroll">
        <div
          className="environment-chart"
          role="group"
          aria-label={t('{{value0}} timeline. Hover to preview a reading, click to select it.', {
            value0: config.title,
          })}
          style={{ minWidth: forecast ? chartWidth : 0 }}
        >
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart
              data={timeline}
              margin={{ top: 48, right: 54, bottom: 28, left: 6 }}
              accessibilityLayer
              onClick={selectPoint}
            >
              <defs>
                <linearGradient id={strokeId} x1="0" y1="0" x2="1" y2="0">
                  {timeline.map((record, index) => (
                    <stop
                      key={record.date}
                      offset={`${(index / Math.max(1, timeline.length - 1)) * 100}%`}
                      stopColor={cropRiskColors[weatherReadingRisk(record, metric)]}
                    />
                  ))}
                </linearGradient>
                <linearGradient id={lowStrokeId} x1="0" y1="0" x2="1" y2="0">
                  {timeline.map((record, index) => (
                    <stop
                      key={record.date}
                      offset={`${(index / Math.max(1, timeline.length - 1)) * 100}%`}
                      stopColor={cropRiskColors[weatherReadingRisk(record, metric, true)]}
                    />
                  ))}
                </linearGradient>
              </defs>
              <XAxis
                dataKey="date"
                tickFormatter={dateLabel}
                interval={forecast ? 0 : 'preserveStartEnd'}
                tick={{ fill: '#435746', fontSize: 14 }}
                axisLine={false}
                tickLine={false}
                minTickGap={18}
                padding={{ left: 64, right: 64 }}
                dy={10}
              />
              <YAxis
                yAxisId="value"
                domain={[minimum, maximum]}
                tick={{ fill: '#435746', fontSize: 14, fontWeight: 600 }}
                axisLine={false}
                tickLine={false}
                width={metric === 'wind' ? 84 : 70}
                tickCount={7}
                tickFormatter={(value) => formatWeatherValue(Number(value), unit)}
              />
              {bounds && (
                <ReferenceArea
                  yAxisId="value"
                  y1={minimum}
                  y2={maximum}
                  shape={
                    <WeatherRiskBackground
                      records={timeline}
                      metric={metric}
                      bounds={bounds}
                      minimum={minimum}
                      maximum={maximum}
                      padding={64}
                    />
                  }
                  fillOpacity={1}
                  stroke="none"
                />
              )}
              <CartesianGrid vertical stroke="#789075" strokeOpacity={0.2} />
              {bounds && (
                <Line
                  yAxisId="value"
                  type="linear"
                  dataKey={(record: WeatherRecord) =>
                    weatherDayBounds(record, metric, bounds)?.criticalLow ?? null
                  }
                  stroke="#c7362f"
                  strokeWidth={2}
                  strokeDasharray="7 4"
                  dot={false}
                  activeDot={false}
                  isAnimationActive={false}
                  connectNulls={false}
                >
                  <LabelList
                    dataKey={(record: WeatherRecord) =>
                      weatherDayBounds(record, metric, bounds)?.criticalLow ?? null
                    }
                    content={<WeatherBoundaryLabel count={timeline.length} unit={unit} />}
                  />
                </Line>
              )}
              {bounds && (
                <Line
                  yAxisId="value"
                  type="linear"
                  dataKey={(record: WeatherRecord) =>
                    weatherDayBounds(record, metric, bounds)?.criticalHigh ?? null
                  }
                  stroke="#c7362f"
                  strokeWidth={2}
                  strokeDasharray="7 4"
                  dot={false}
                  activeDot={false}
                  isAnimationActive={false}
                  connectNulls={false}
                >
                  <LabelList
                    dataKey={(record: WeatherRecord) =>
                      weatherDayBounds(record, metric, bounds)?.criticalHigh ?? null
                    }
                    content={<WeatherBoundaryLabel count={timeline.length} unit={unit} />}
                  />
                </Line>
              )}
              <Tooltip
                content={<WeatherChartTooltip metric={metric} units={units} />}
                cursor={{ stroke: '#243b4d', strokeDasharray: '4 4' }}
              />
              {today && (
                <ReferenceLine
                  yAxisId="value"
                  x={today.date}
                  stroke="#315e40"
                  strokeWidth={2}
                  label={{
                    value: t('Today'),
                    position: 'insideTopLeft',
                    fill: '#315e40',
                    fontWeight: 600,
                  }}
                />
              )}
              <ReferenceLine
                yAxisId="value"
                x={selected.date}
                stroke="#243b4d"
                strokeWidth={2}
                strokeOpacity={0.35}
              />
              <Line
                yAxisId="value"
                type="monotone"
                dataKey={metric}
                stroke={`url(#${strokeId})`}
                strokeWidth={forecast ? 4.5 : 3.5}
                strokeDasharray={forecast ? '8 4' : undefined}
                dot={
                  <WeatherValueDot
                    metric={metric}
                    selectedKey={selected.key}
                    showPoints={forecast || records.length <= 14}
                  />
                }
                activeDot={{ r: 7, stroke: '#fff', strokeWidth: 3 }}
                connectNulls={false}
                isAnimationActive={animate}
                animationDuration={450}
              >
                <LabelList
                  dataKey={metric}
                  content={
                    <WeatherValueLabel
                      metric={metric}
                      records={timeline}
                      unit={unit}
                      selectedKey={selected.key}
                    />
                  }
                />
              </Line>
              {metric === 'temperature' && (
                <Line
                  yAxisId="value"
                  type="monotone"
                  dataKey="low"
                  stroke={`url(#${lowStrokeId})`}
                  strokeWidth={2}
                  strokeDasharray="3 4"
                  connectNulls={false}
                  isAnimationActive={animate}
                  dot={
                    <WeatherValueDot
                      metric={metric}
                      selectedKey={selected.key}
                      low
                      showPoints={forecast || records.length <= 14}
                    />
                  }
                >
                  <LabelList
                    dataKey="low"
                    content={
                      <WeatherValueLabel
                        metric={metric}
                        records={timeline}
                        unit={unit}
                        selectedKey={selected.key}
                        low
                      />
                    }
                  />
                </Line>
              )}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}

type CropRiskLegendProps = { assessment: CropAssessment };

function CropRiskLegend({ assessment }: CropRiskLegendProps) {
  const { t } = useTranslation();
  const { crop, soilCoverage } = assessment.context;
  const labels = [
    { label: 'Good range', color: cropRiskColors.good },
    { label: 'Caution', color: cropRiskColors.caution },
    { label: 'High risk', color: cropRiskColors.high },
  ];

  return (
    <div className="weather-crop-legend">
      {assessment.model.kind === 'rule_engine' && (
        <p className="weather-crop-note">
          {t('General growing-season limits for {{crop}}.', { crop })}
        </p>
      )}
      <ul aria-label={t('Crop risk legend')}>
        {labels.map(({ label, color }) => (
          <li key={label}>
            <span
              className="weather-crop-swatch"
              style={{ backgroundColor: color }}
              aria-hidden="true"
            />
            {t(label)}
          </li>
        ))}
        <li>
          <span className="weather-crop-limit-swatch" aria-hidden="true" />
          {t('Critical limit')}
        </li>
      </ul>
      {soilCoverage === 'partial' && (
        <p className="weather-crop-note">
          {t('Field soil data is incomplete. Limits use the available soil properties.')}
        </p>
      )}
      {soilCoverage === 'unavailable' && (
        <p className="weather-crop-note">
          {t('Field soil data is unavailable. Limits use crop and weather data.')}
        </p>
      )}
    </div>
  );
}
