import { Descriptions, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import type { RotationAdvice, RotationCandidate } from '../../../types/rotation/rotation.types.ts';
import {
  calendarKindLabels,
  soilIndicatorLabels,
  stageLabels,
} from '../constants/rotationLabels.ts';
import {
  cropLabelMap,
  formatDayOfYear,
  formatNumber,
  formatUsd,
  formatValue,
  seasonYear,
} from '../utils/rotationPresentation.ts';
import { FindingList } from './FindingList';
import { InformationGaps } from './InformationGaps';
import { LocalTiming } from './LocalTiming';

type CandidateDetailsProps = { advice: RotationAdvice; candidate: RotationCandidate };

export function CandidateDetails({ advice, candidate }: CandidateDetailsProps) {
  const { t, i18n } = useTranslation();
  const language = i18n.language;
  const year = seasonYear(advice);
  const cropLabels = cropLabelMap(advice);
  const stages = Object.entries(candidate.calendar.stages).filter(
    (entry): entry is [string, number] => entry[1] !== null,
  );
  const { revenue } = candidate;
  const cropYield = candidate.yield;
  const timing = advice.seasonTiming;
  const cropTiming = timing?.crops[candidate.crop];

  return (
    <div className="rotation-candidate-details">
      <FindingList title={t('Risks')} findings={candidate.risks} cropLabels={cropLabels} />
      {candidate.risks.length === 0 && (
        <Typography.Paragraph type="secondary">
          {t('No rotation risks were found with the information available.')}
        </Typography.Paragraph>
      )}
      <FindingList title={t('Benefits')} findings={candidate.benefits} cropLabels={cropLabels} />
      <FindingList
        title={t('Worth considering')}
        findings={candidate.advisories}
        cropLabels={cropLabels}
      />
      <section>
        <Typography.Title level={5}>{t('Yield and gross revenue')}</Typography.Title>
        {cropYield ? (
          <Descriptions
            column={{ xs: 1, md: 2 }}
            size="small"
            items={yieldItems(candidate, t, language)}
          />
        ) : (
          <Typography.Paragraph type="secondary">
            {t('No yield or revenue estimate is available for this crop here.')}
          </Typography.Paragraph>
        )}
        {revenue && (
          <Typography.Text type="secondary">
            {t('Gross revenue only: seed, fertiliser, fuel and other costs are not subtracted.')}
          </Typography.Text>
        )}
      </section>
      {stages.length > 0 && (
        <section>
          <Typography.Title level={5}>{t('Typical season')}</Typography.Title>
          <ol className="rotation-stages">
            {stages.map(([stage, day]) => (
              <li key={stage}>
                <Typography.Text type="secondary">{t(stageLabels[stage] ?? stage)}</Typography.Text>
                <Typography.Text strong>{formatDayOfYear(day, year, language)}</Typography.Text>
              </li>
            ))}
          </ol>
          <Typography.Text type="secondary">
            {t(calendarKindLabels[candidate.calendar.kind] ?? candidate.calendar.kind)}
          </Typography.Text>
        </section>
      )}
      {timing && cropTiming && <LocalTiming timing={timing} crop={cropTiming} year={year} />}
      {candidate.soil.length > 0 && (
        <section>
          <Typography.Title level={5}>{t('Effect on the soil')}</Typography.Title>
          <Descriptions
            column={{ xs: 1, md: 2 }}
            size="small"
            items={candidate.soil.map((indicator) => ({
              key: indicator.id,
              label: t(soilIndicatorLabels[indicator.id] ?? indicator.id),
              children: formatValue(indicator.value, t, language),
            }))}
          />
        </section>
      )}
      <InformationGaps title={t('Information gaps for this crop')} gaps={candidate.dataGaps} />
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
