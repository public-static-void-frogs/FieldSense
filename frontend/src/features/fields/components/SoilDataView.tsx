import { Segmented, Tooltip } from 'antd';
import { CircleHelp } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
} from 'recharts';

const colors = ['#386a49', '#336f9c', '#a05b26', '#834d8b', '#a33d51', '#59671e', '#536c76'];

type SoilChartRow = {
  label: string;
  detail?: string;
  values: Record<string, number | null | undefined>;
};

type SoilChartSeries = { key: string; label: string; count?: boolean };

type SoilDataViewProps = {
  title: string;
  help?: string;
  rows: SoilChartRow[];
  series: SoilChartSeries[];
  kind?: 'bar' | 'line';
  unit?: string;
  children: ReactNode;
};

export function SoilDataView({
  title,
  help,
  rows,
  series,
  kind = 'bar',
  unit,
  children,
}: SoilDataViewProps) {
  const { t, i18n } = useTranslation();
  const [view, setView] = useState<'table' | 'chart'>('table');
  const Chart = kind === 'line' ? LineChart : BarChart;
  const format = new Intl.NumberFormat(i18n.language, { maximumFractionDigits: 4 });
  const hasCounts = series.some(({ count }) => count);
  const hasValues = rows.some(({ values }) => Object.values(values).some((value) => value != null));

  return (
    <div className="field-insights-panel">
      <div className="field-insights-data-toolbar">
        <span className="field-insights-help-label">
          <strong>{title}</strong>
          {help && (
            <Tooltip title={help} trigger={['hover', 'focus', 'click']}>
              <button
                type="button"
                className="field-insights-help-button"
                aria-label={t('About {{label}}', { label: title })}
              >
                <CircleHelp size={16} aria-hidden="true" />
              </button>
            </Tooltip>
          )}
        </span>
        <Segmented<'table' | 'chart'>
          size="small"
          aria-label={t('View for {{label}}', { label: title })}
          value={view}
          onChange={setView}
          options={[
            { value: 'table', label: t('Table') },
            { value: 'chart', label: t('Chart') },
          ]}
        />
      </div>
      <div hidden={view !== 'table'}>{hasValues ? children : <span>{t('No data')}</span>}</div>
      {view === 'chart' && !hasValues && <span>{t('No data')}</span>}
      {view === 'chart' && hasValues && (
        <div className="field-insights-data-chart" role="group" aria-label={title}>
          {unit && <small className="field-insights-muted">{unit}</small>}
          <ResponsiveContainer width="100%" height={250}>
            <Chart data={rows} accessibilityLayer margin={{ top: 8, right: 12 }}>
              <CartesianGrid stroke="#e1e8dd" vertical={false} />
              <XAxis
                dataKey="label"
                minTickGap={24}
                tick={{ fontSize: 12 }}
                tickFormatter={(value: string) => value.replace(/^(\d{4})-(\d{2}-\d{2})/, '$2')}
              />
              <YAxis yAxisId="value" width={46} tick={{ fontSize: 12 }} />
              {hasCounts && (
                <YAxis yAxisId="count" orientation="right" width={32} allowDecimals={false} />
              )}
              <ChartTooltip
                labelFormatter={(label, entries) => {
                  const detail = entries[0]?.payload?.detail;

                  return detail ? `${label} · ${detail}` : String(label ?? '');
                }}
                formatter={(value) => (typeof value === 'number' ? format.format(value) : '—')}
              />
              {series.length > 1 && <Legend />}
              {series.map(({ key, label, count }, index) => {
                const color = colors[index % colors.length];
                const props = {
                  dataKey: `values.${key}`,
                  name: label,
                  yAxisId: count ? 'count' : 'value',
                  isAnimationActive: false,
                };
                if (kind === 'bar') {
                  return <Bar key={key} {...props} fill={color} maxBarSize={48} />;
                }

                return (
                  <Line
                    key={key}
                    {...props}
                    stroke={color}
                    strokeWidth={2}
                    dot={rows.length <= 31}
                  />
                );
              })}
            </Chart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
