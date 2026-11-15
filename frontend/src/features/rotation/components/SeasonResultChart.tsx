import { useTranslation } from 'react-i18next';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { RotationAdvice, RotationPlanStep } from '../../../types/rotation/rotation.types.ts';
import { cropNamer, formatSignedUsd } from '../utils/planPresentation.ts';
import { formatNumber } from '../utils/rotationPresentation.ts';

const series = [
  { key: 'revenueUsdPerAcre', label: 'Sales', color: '#2a78d6' },
  { key: 'costUsdPerAcre', label: 'Cost', color: '#c46a21' },
  { key: 'netUsdPerAcre', label: 'Average result', color: '#47794c' },
  { key: 'worstYearUsdPerAcre', label: 'Worst year', color: '#8558a4' },
] as const;

type SeasonResultChartProps = { advice: RotationAdvice; steps: RotationPlanStep[] };

export function SeasonResultChart({ advice, steps }: SeasonResultChartProps) {
  const { t, i18n } = useTranslation();
  const name = cropNamer(advice);
  const usd = (value: number) => formatSignedUsd(value, i18n.language);

  return (
    <figure className="rotation-season-chart">
      <figcaption>{t('USD per acre')}</figcaption>
      <ul className="rotation-outcomes-legend">
        {series.map(({ key, label, color }) => (
          <li key={key}>
            <span style={{ backgroundColor: color }} />
            {t(label)}
          </li>
        ))}
      </ul>
      <ResponsiveContainer
        width="100%"
        height={220}
        minWidth={0}
        initialDimension={{ width: 640, height: 220 }}
      >
        <BarChart data={steps} accessibilityLayer margin={{ top: 8, right: 12 }} barGap={3}>
          <CartesianGrid stroke="#e1e8dd" vertical={false} />
          <XAxis dataKey="season" tick={{ fontSize: 12 }} tickLine={false} />
          <YAxis width="auto" tick={{ fontSize: 12 }} tickLine={false} tickFormatter={usd} />
          <ReferenceLine y={0} stroke="#58664d" />
          <Tooltip
            cursor={{ fill: '#f0f3ea' }}
            content={({ active, payload }) => {
              const step = payload?.[0]?.payload as RotationPlanStep | undefined;
              if (!active || !step) {
                return null;
              }

              return (
                <div className="rotation-outcomes-tooltip">
                  <strong>{`${step.season} · ${t(name(step.crop))}`}</strong>
                  {series.map(({ key, label }) => (
                    <span key={key}>
                      {t(label)}: {usd(step[key])}
                      {key === 'worstYearUsdPerAcre' && ` (${step.worstYear})`}
                    </span>
                  ))}
                  <span>
                    {t('Yield: {{value}} {{unit}}', {
                      value: formatNumber(step.yieldPerAcre, i18n.language),
                      unit: step.yieldUnit,
                    })}
                  </span>
                </div>
              );
            }}
          />
          {series.map(({ key, label, color }) => (
            <Bar
              key={key}
              dataKey={key}
              name={t(label)}
              fill={color}
              maxBarSize={28}
              radius={2}
              isAnimationActive={false}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </figure>
  );
}
