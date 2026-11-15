import { useTranslation } from 'react-i18next';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { RotationSimulatedOutcome } from '../../../types/rotation/rotation.types.ts';
import { yieldModeLabels } from '../constants/rotationLabels.ts';
import { formatSignedUsd } from '../utils/planPresentation.ts';
import { formatNumber, formatPercent } from '../utils/rotationPresentation.ts';

// Blue and orange stay apart for colour-blind readers; the bar's side of zero says the same.
const OUTCOME_COLORS = { profit: '#2a78d6', loss: '#d4651f' };

type OutcomeChartProps = {
  outcomes: RotationSimulatedOutcome[];
  yieldUnit: string;
  label: string;
};

/** Net result of the first season under each past year's weather and price. */
export function OutcomeChart({ outcomes, yieldUnit, label }: OutcomeChartProps) {
  const { t, i18n } = useTranslation();
  const language = i18n.language;
  const rows = [...outcomes].sort((left, right) => left.year - right.year);

  return (
    <figure className="rotation-outcomes" role="group" aria-label={label}>
      <ul className="rotation-outcomes-legend">
        <li>
          <span style={{ background: OUTCOME_COLORS.profit }} />
          {t('Profit')}
        </li>
        <li>
          <span style={{ background: OUTCOME_COLORS.loss }} />
          {t('Loss')}
        </li>
      </ul>
      <ResponsiveContainer
        width="100%"
        height={260}
        minWidth={0}
        initialDimension={{ width: 640, height: 260 }}
      >
        <BarChart data={rows} accessibilityLayer margin={{ top: 8, right: 12 }} barCategoryGap={2}>
          <CartesianGrid stroke="#e1e8dd" vertical={false} />
          <XAxis dataKey="year" minTickGap={16} tick={{ fontSize: 12 }} tickLine={false} />
          <YAxis
            width="auto"
            tick={{ fontSize: 12 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(value: number) => formatSignedUsd(value, language)}
          />
          <ReferenceLine y={0} stroke="#58664d" />
          <Tooltip
            cursor={{ fill: '#f0f3ea' }}
            content={({ active, payload }) => {
              const row = payload?.[0]?.payload as RotationSimulatedOutcome | undefined;
              if (!active || !row) {
                return null;
              }

              return (
                <div className="rotation-outcomes-tooltip">
                  <strong>{t('If {{year}} came again', { year: row.year })}</strong>
                  <span>
                    {t('Result: {{amount}} per acre', {
                      amount: formatSignedUsd(row.netUsdPerAcre, language),
                    })}
                  </span>
                  <span>
                    {t('Yield: {{value}} {{unit}}', {
                      value: formatNumber(row.yieldPerAcre, language),
                      unit: yieldUnit,
                    })}{' '}
                    ({t(yieldModeLabels[row.yieldMode] ?? row.yieldMode)})
                  </span>
                  <span>
                    {t('Price: {{amount}}', { amount: formatNumber(row.priceUsd, language, 2) })}
                  </span>
                  <span>
                    {t('Weight in the forecast: {{share}}', {
                      share: formatPercent(row.probability, language),
                    })}
                  </span>
                </div>
              );
            }}
          />
          <Bar dataKey="netUsdPerAcre" isAnimationActive={false} maxBarSize={24} radius={2}>
            {rows.map((row) => (
              <Cell
                key={row.year}
                fill={row.netUsdPerAcre < 0 ? OUTCOME_COLORS.loss : OUTCOME_COLORS.profit}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </figure>
  );
}
