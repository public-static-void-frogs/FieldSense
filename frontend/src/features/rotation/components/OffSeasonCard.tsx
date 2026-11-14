import { Card, Flex, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import type {
  RotationAdvice,
  RotationOffSeasonOption,
  RotationWaterAtSowing,
} from '../../../types/rotation/rotation.types.ts';
import {
  cropLabelMap,
  formatDayOfYear,
  formatNumber,
  formatPercent,
  seasonYear,
} from '../utils/rotationPresentation.ts';

type OffSeasonCardProps = { advice: RotationAdvice };

const levelTags = {
  reliable: { color: 'green', label: 'Works in most years' },
  marginal: { color: 'gold', label: 'Works in some years' },
  unlikely: { color: 'red', label: 'Rarely works' },
} as const;

const emptyReasons = {
  previous_crop_unknown:
    'The last crop on this field is not known, so the time left after harvest could not be estimated.',
  no_harvest_in_calendar:
    'The field is under a standing perennial crop or has no harvest date, so there is no gap after harvest to fill.',
  no_weather_record: 'No long weather record is available for this location.',
  weather_record_too_short: 'No long weather record is available for this location.',
} as const;

/** What can be established between the last crop's harvest and winter. */
export function OffSeasonCard({ advice }: OffSeasonCardProps) {
  const { t, i18n } = useTranslation();
  const slot = advice.offSeason;
  if (!slot) {
    return null;
  }
  const language = i18n.language;
  const year = seasonYear(advice) - 1; // the autumn before the season being planned
  const crop = slot.afterCrop ? t(cropLabelMap(advice)[slot.afterCrop] ?? slot.afterCrop) : '';
  const record = advice.weatherRecord;
  const water = slot.afterCrop ? advice.seasonTiming?.waterAtSowing[slot.afterCrop] : undefined;
  const emptyReason = slot.status === 'ok' ? 'no_harvest_in_calendar' : slot.status;
  const waterTag = water?.coverOk
    ? { color: 'green', label: 'Water-safe' }
    : { color: 'orange', label: 'Can leave the soil short of water' };

  return (
    <Card title={t('After harvest: cover crops and fall-sown crops')}>
      {slot.status !== 'ok' || slot.harvestDoy === null || slot.seedingDoy === null ? (
        <Typography.Paragraph type="secondary">{t(emptyReasons[emptyReason])}</Typography.Paragraph>
      ) : (
        <>
          <Typography.Paragraph>
            {t(
              '{{crop}} is usually harvested around {{harvest}}, so the next seeding is possible from about {{seeding}}.',
              {
                crop,
                harvest: formatDayOfYear(slot.harvestDoy, year, language),
                seeding: formatDayOfYear(slot.seedingDoy, year, language),
              },
            )}{' '}
            {slot.firstKillingFrostDoy !== null &&
              t('The first hard freeze typically comes around {{frost}}.', {
                frost: formatDayOfYear(slot.firstKillingFrostDoy, year, language),
              })}
          </Typography.Paragraph>
          <Flex vertical gap={12} component="ul" className="rotation-off-season">
            {slot.options.map((option) => (
              <li key={option.id}>
                <Flex gap={8} align="center" wrap>
                  <Typography.Text strong>{t(option.label)}</Typography.Text>
                  <Tag color={levelTags[option.level].color}>
                    {t(levelTags[option.level].label)}
                  </Tag>
                </Flex>
                <Typography.Text type="secondary">
                  {optionDetail(option, t, language)}
                </Typography.Text>
              </li>
            ))}
          </Flex>
          {water && water.cover.shortfall !== null && water.bare.shortfall !== null && (
            <Typography.Paragraph>
              <Typography.Text strong>{t('Soil water after a rye cover crop')}</Typography.Text>{' '}
              <Tag color={waterTag.color}>{t(waterTag.label)}</Tag>
              <br />
              <Typography.Text type="secondary">
                {waterDetail(water, crop, t, language)}
              </Typography.Text>
            </Typography.Paragraph>
          )}
          <Typography.Text type="secondary">
            {record &&
              t(
                'Counted over {{seasons}} years of past weather near this field ({{first}}–{{last}}), not a forecast for this autumn.',
                { seasons: record.seasons, first: record.firstYear, last: record.lastYear },
              )}{' '}
            {t('Harvest dates are regional medians; an earlier harvest leaves more time.')}
          </Typography.Text>
        </>
      )}
    </Card>
  );
}

function waterDetail(
  water: RotationWaterAtSowing,
  crop: string,
  t: (key: string, options?: Record<string, unknown>) => string,
  language: string,
) {
  const shares = t(
    'After {{crop}}, the soil is short of water at the next sowing in {{cover}} of years with a rye cover crop and {{bare}} without one ({{years}} years of weather).',
    {
      crop,
      cover: formatPercent(water.cover.shortfall ?? 0, language),
      bare: formatPercent(water.bare.shortfall ?? 0, language),
      years: water.years,
    },
  );
  if (water.safeAutumnRainMm === null) {
    return `${shares} ${t('No amount of autumn rain makes the cover crop water-safe here.')}`;
  }
  if (water.safeAutumnRainMm <= 0) {
    return shares;
  }
  const rain = t(
    'It is water-safe when autumn rain reaches {{rain}} mm; {{typical}} mm is typical.',
    {
      rain: formatNumber(water.safeAutumnRainMm, language, 0),
      typical: formatNumber(water.autumnRainTypicalMm ?? 0, language, 0),
    },
  );

  return `${shares} ${rain}`;
}

function optionDetail(
  option: RotationOffSeasonOption,
  t: (key: string, options?: Record<string, unknown>) => string,
  language: string,
) {
  const counts = t('Enough autumn left in {{met}} of {{total}} past years.', {
    met: option.seasonsMet,
    total: option.seasonsTotal,
  });
  const values = {
    typical: formatNumber(option.typical, language, 0),
    minimum: formatNumber(option.minimum, language, 0),
  };
  const detail =
    option.metric === 'fall_gdd0'
      ? t(
          'Typical warmth after seeding: {{typical}} growing degree days; it needs {{minimum}}.',
          values,
        )
      : t('Typically {{typical}} days before the first hard freeze; it needs {{minimum}}.', values);
  return `${counts} ${detail}`;
}
