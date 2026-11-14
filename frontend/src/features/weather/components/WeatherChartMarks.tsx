import type { WeatherMetric, WeatherRecord } from '../../../types/weather/weather.types.ts';
import {
  cropRiskColors,
  cropRiskLabelStyles,
  weatherReadingRisk,
} from '../utils/cropRiskPresentation.ts';
import { formatWeatherValue } from '../utils/weatherPresentation.ts';

type WeatherValueDotProps = {
  cx?: number;
  cy?: number;
  payload?: WeatherRecord;
  metric: WeatherMetric;
  selectedKey: number;
  low?: boolean;
  showPoints?: boolean;
};

export function WeatherValueDot({
  cx,
  cy,
  payload,
  metric,
  selectedKey,
  low = false,
  showPoints = true,
}: WeatherValueDotProps) {
  if (cx === undefined || cy === undefined || !payload) {
    return null;
  }
  const risk = weatherReadingRisk(payload, metric, low);
  const selected = payload.key === selectedKey;
  const color = cropRiskColors[risk];
  if (!showPoints && !selected) {
    return null;
  }

  return (
    <g>
      {selected && <circle cx={cx} cy={cy} r={12} fill="white" stroke="#243b4d" strokeWidth={2} />}
      <circle cx={cx} cy={cy} r={selected ? 8 : 6} fill={color} stroke="white" strokeWidth={3} />
    </g>
  );
}

type WeatherValueLabelProps = {
  x?: number | string;
  y?: number | string;
  index?: number;
  metric: WeatherMetric;
  records: WeatherRecord[];
  unit: string;
  selectedKey: number;
  low?: boolean;
};

export function WeatherValueLabel({
  x,
  y,
  index,
  metric,
  records,
  unit,
  selectedKey,
  low = false,
}: WeatherValueLabelProps) {
  const record = records[index ?? -1];
  if (!record || typeof x !== 'number' || typeof y !== 'number') {
    return null;
  }
  const value = low ? record.low : record[metric];
  if (value === null) {
    return null;
  }
  const risk = weatherReadingRisk(record, metric, low);
  const alert = risk === 'high' || risk === 'caution';
  if (low && !alert) {
    return null;
  }
  if (records.length > 14 && record.key !== selectedKey) {
    return null;
  }
  const number = formatWeatherValue(value);
  const text = `${alert ? '⚠ ' : ''}${number}`;
  const width = number.length * 8.5 + unit.length * 6 + (alert ? 18 : 0) + 22;
  const colors = cropRiskLabelStyles[risk];
  const offset = low ? 18 : -42;

  return (
    <g
      className="weather-value-label"
      data-selected={record.key === selectedKey}
      transform={`translate(${x},${y + offset})`}
      pointerEvents="none"
    >
      <rect
        x={-width / 2}
        y={0}
        width={width}
        height={30}
        rx={7}
        fill={colors.fill}
        stroke={colors.stroke}
        strokeWidth={1.4}
      />
      <text x={0} y={20} textAnchor="middle" fill={colors.text} fontSize={14} fontWeight={700}>
        {text}
        <tspan fontSize={11.5} fontWeight={600}>
          {' '}
          {unit}
        </tspan>
      </text>
    </g>
  );
}

type WeatherBoundaryLabelProps = {
  x?: number | string;
  y?: number | string;
  value?: number | string;
  index?: number;
  count: number;
  unit: string;
};

export function WeatherBoundaryLabel({
  x,
  y,
  value,
  index,
  count,
  unit,
}: WeatherBoundaryLabelProps) {
  if (
    index !== count - 1 ||
    typeof x !== 'number' ||
    typeof y !== 'number' ||
    typeof value !== 'number'
  ) {
    return null;
  }

  return (
    <text x={x + 56} y={y + 18} textAnchor="end" fill="#a32120" fontSize={13} pointerEvents="none">
      ⚠ {formatWeatherValue(value, unit)}
    </text>
  );
}
