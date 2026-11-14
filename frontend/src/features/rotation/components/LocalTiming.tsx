import { Descriptions, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import type {
  RotationCropTiming,
  RotationSeasonTiming,
  RotationTimingWindow,
} from '../../../types/rotation/rotation.types.ts';
import { formatIsoDay, formatNumber, formatPercent } from '../utils/rotationPresentation.ts';

type LocalTimingProps = { timing: RotationSeasonTiming; crop: RotationCropTiming; year: number };

type Translate = (key: string, options?: Record<string, unknown>) => string;

const stageRows = [
  ['firstWorkable', 'First workable sowing day'],
  ['sow', 'Sowing'],
  ['flower', 'Flowering'],
  ['mature', 'Maturity'],
] as const;

const scenarioLabels = { ssp245: 'middle emissions', ssp585: 'high emissions' } as const;

/** Sowing windows and heat / frost risk from past weather around the field (M3). */
export function LocalTiming({ timing, crop, year }: LocalTimingProps) {
  const { t, i18n } = useTranslation();
  const language = i18n.language;
  const range = (window: RotationTimingWindow) =>
    t('typically around {{typical}}, usually {{early}} – {{late}}', {
      typical: formatIsoDay(`${year}-${window.typical}`, language),
      early: formatIsoDay(`${year}-${window.early}`, language),
      late: formatIsoDay(`${year}-${window.late}`, language),
    });
  const frosts = [
    ['Last spring frost', timing.lastSpringFrost],
    ['First autumn frost', timing.firstAutumnFrost],
  ] as const;
  const dates = [
    ...frosts.slice(0, 1),
    ...stageRows.map(([stage, label]) => [label, crop.stages[stage] ?? null] as const),
    ...frosts.slice(1),
  ].flatMap(([label, window]) =>
    window ? [{ key: label, label: t(label), children: range(window) }] : [],
  );
  const errors = Object.values(crop.dateErrorDays);

  return (
    <section>
      <Typography.Title level={5}>{t('Local timing and weather risk')}</Typography.Title>
      <Descriptions column={1} size="small" items={[...dates, ...riskItems(crop, t, language)]} />
      <Typography.Text type="secondary">
        {timing.matchLevel === 'field'
          ? t('From past weather around this field, not a forecast for this season.')
          : t(
              'From past weather for the wider area (about 50 km), not a forecast for this season.',
            )}{' '}
        {errors.length > 0 &&
          t('Dates can be off by about {{days}} days against USDA crop progress reports.', {
            days: formatNumber(Math.max(...errors), language, 0),
          })}{' '}
        {t('Only the sowing date is used in the ranking; the rest is for information.')}
      </Typography.Text>
    </section>
  );
}

function riskItems(crop: RotationCropTiming, t: Translate, language: string) {
  const heat = crop.heatAtFlowering;
  const items = [];
  if (heat.probability !== null) {
    items.push({
      key: 'heat',
      label: t('Heat during flowering'),
      children: (
        <>
          {t('{{share}} of years have 2 or more days at 35 °C or hotter', {
            share: formatPercent(heat.probability, language),
          })}{' '}
          {heat.vulnerable && <Tag color="orange">{t('Heat-exposed')}</Tag>}
        </>
      ),
    });
  }
  if (crop.frostBeforeMaturity !== null) {
    items.push({
      key: 'frost',
      label: t('Frost before maturity'),
      children: t('{{share}} of years', {
        share: formatPercent(crop.frostBeforeMaturity, language),
      }),
    });
  }
  items.push({
    key: 'delay',
    label: t('Room to delay sowing'),
    children: delayText(crop.sowingDelayMarginDays, t, language),
  });
  if (crop.workableDays.typical !== null) {
    items.push({
      key: 'workable',
      label: t('Workable sowing days'),
      children: workableText(crop, t, language),
    });
  }
  for (const outlook of crop.outlook2040) {
    if (outlook.heatMedian !== null && outlook.heatMin !== null && outlook.heatMax !== null) {
      items.push({
        key: outlook.scenario,
        label: t('Heat during flowering by 2040, {{scenario}}', {
          scenario: t(scenarioLabels[outlook.scenario]),
        }),
        children: t('{{share}} of years ({{low}} – {{high}} across {{count}} climate models)', {
          share: formatPercent(outlook.heatMedian, language),
          low: formatPercent(outlook.heatMin, language),
          high: formatPercent(outlook.heatMax, language),
          count: outlook.models,
        }),
      });
    }
  }

  return items;
}

function delayText(days: number | null, t: Translate, language: string) {
  if (days === null) {
    return t('No safe delay: frost before maturity is already likely at the typical date');
  }
  if (days === 0) {
    return t('None: a later sowing raises frost or heat risk');
  }

  return t('Up to {{days}} days', { days: formatNumber(days, language, 0) });
}

function workableText(crop: RotationCropTiming, t: Translate, language: string) {
  const { low, typical, high } = crop.workableDays;
  if (typical === null || low === null || high === null) {
    return '';
  }

  return t('typically {{typical}}, usually {{low}} – {{high}}', {
    typical: formatNumber(typical, language, 0),
    low: formatNumber(low, language, 0),
    high: formatNumber(high, language, 0),
  });
}
