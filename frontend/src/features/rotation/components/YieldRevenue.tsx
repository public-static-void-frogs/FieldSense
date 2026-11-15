import { Descriptions, Segmented, Typography } from 'antd';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { RotationCandidate } from '../../../types/rotation/rotation.types.ts';
import { formatNumber, formatUsd } from '../utils/rotationPresentation.ts';

type YieldRevenueProps = { candidate: RotationCandidate };

export function YieldRevenue({ candidate }: YieldRevenueProps) {
  const { t, i18n } = useTranslation();
  const [view, setView] = useState<'data' | 'chart'>('data');
  const { yield: cropYield, revenue } = candidate;
  const title = t('Yield and gross revenue');
  const items = yieldItems(candidate, t, i18n.language);

  return (
    <section>
      <div className="rotation-section-toolbar">
        <Typography.Title level={5}>{title}</Typography.Title>
        {cropYield && (
          <Segmented<'data' | 'chart'>
            size="small"
            aria-label={t('View for {{label}}', { label: title })}
            value={view}
            onChange={setView}
            options={[
              { label: t('Data'), value: 'data' },
              { label: t('Chart'), value: 'chart' },
            ]}
          />
        )}
      </div>
      {!cropYield && (
        <Typography.Paragraph type="secondary">
          {t('No yield or revenue estimate is available for this crop here.')}
        </Typography.Paragraph>
      )}
      {cropYield && view === 'data' && (
        <Descriptions column={{ xs: 1, md: 2 }} size="small" items={items} />
      )}
      {cropYield && view === 'chart' && (
        <div className="rotation-estimate-chart">
          <EstimateRange
            label={t('Expected yield')}
            low={cropYield.low}
            expected={cropYield.mid}
            high={cropYield.high}
            format={(value) => `${formatNumber(value, i18n.language)} ${cropYield.unit}`}
          />
          {revenue && (
            <EstimateRange
              label={t('Gross revenue for the field')}
              low={revenue.lowUsd}
              expected={revenue.midUsd}
              high={revenue.highUsd}
              format={(value) => formatUsd(value, i18n.language)}
            />
          )}
          <Descriptions
            column={{ xs: 1, md: 2 }}
            size="small"
            items={items.filter(({ key }) => key === 'basis' || key === 'price')}
          />
        </div>
      )}
      {revenue && (
        <details className="strategy-disclosure">
          <summary>{t('About {{label}}', { label: title })}</summary>
          <Typography.Text type="secondary">
            {t('Gross revenue only: seed, fertiliser, fuel and other costs are not subtracted.')}
          </Typography.Text>
        </details>
      )}
    </section>
  );
}

type EstimateRangeProps = {
  label: string;
  low: number;
  expected: number;
  high: number;
  format: (value: number) => string;
};

function EstimateRange({ label, low, expected, high, format }: EstimateRangeProps) {
  const { t } = useTranslation();
  const position = high > low ? ((expected - low) / (high - low)) * 100 : 50;

  return (
    <div className="rotation-estimate-range">
      <strong>{label}</strong>
      <div className="rotation-estimate-track" aria-hidden="true">
        <span style={{ left: `${Math.min(100, Math.max(0, position))}%` }} />
      </div>
      <dl className="rotation-estimate-values">
        <div>
          <dt>{t('Low estimate')}</dt>
          <dd>{format(low)}</dd>
        </div>
        <div>
          <dt>{t('Expected estimate')}</dt>
          <dd>{format(expected)}</dd>
        </div>
        <div>
          <dt>{t('High estimate')}</dt>
          <dd>{format(high)}</dd>
        </div>
      </dl>
    </div>
  );
}

type Translate = (key: string, options?: Record<string, unknown>) => string;

function yieldItems(candidate: RotationCandidate, t: Translate, language: string) {
  const cropYield = candidate.yield;
  const { revenue } = candidate;
  if (!cropYield) {
    return [];
  }
  const items = [
    {
      key: 'yield',
      label: t('Expected yield'),
      children: t('{{mid}} {{unit}} (range {{low}} – {{high}})', {
        mid: formatNumber(cropYield.mid, language),
        low: formatNumber(cropYield.low, language),
        high: formatNumber(cropYield.high, language),
        unit: cropYield.unit,
      }),
    },
    {
      key: 'basis',
      label: t('Yield based on'),
      children:
        cropYield.level === 'county'
          ? t('County yield records and trend')
          : t('State yield range, not field records'),
    },
  ];
  if (revenue) {
    items.push(
      {
        key: 'revenue',
        label: t('Gross revenue for the field'),
        children: t('{{mid}} (range {{low}} – {{high}})', {
          mid: formatUsd(revenue.midUsd, language),
          low: formatUsd(revenue.lowUsd, language),
          high: formatUsd(revenue.highUsd, language),
        }),
      },
      {
        key: 'price',
        label: t('Price used'),
        children: t('${{price}} per {{unit}}', {
          price: formatNumber(revenue.priceUsd, language, 2),
          unit: revenue.priceUnit,
        }),
      },
    );
  }

  return items;
}
