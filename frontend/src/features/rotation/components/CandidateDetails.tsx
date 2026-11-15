import { Button, Flex, Tooltip, Typography } from 'antd';
import { CircleHelp } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { RotationAdvice, RotationCandidate } from '../../../types/rotation/rotation.types.ts';
import { calendarKindLabels, stageLabels } from '../constants/rotationLabels.ts';
import { cropLabelMap, formatDayOfYear, seasonYear } from '../utils/rotationPresentation.ts';
import { FindingList } from './FindingList';
import { InformationGaps } from './InformationGaps';
import { LocalTiming } from './LocalTiming';
import { SoilEffects } from './SoilEffects';
import { YieldRevenue } from './YieldRevenue';
import './CandidateDetails.css';

type CandidateDetailsProps = { advice: RotationAdvice; candidate: RotationCandidate };

export function CandidateDetails({ advice, candidate }: CandidateDetailsProps) {
  const { t, i18n } = useTranslation();
  const language = i18n.language;
  const year = seasonYear(advice);
  const cropLabels = cropLabelMap(advice);
  const planting = candidate.calendar.stages.planted;
  const stages = Object.entries(candidate.calendar.stages)
    .filter((entry): entry is [string, number] => entry[1] !== null)
    .map(([stage, day]) => ({
      stage,
      day,
      dateYear: planting != null && day < planting ? year + 1 : year,
    }))
    .sort((left, right) => left.dateYear - right.dateYear || left.day - right.day);
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
      <YieldRevenue candidate={candidate} />
      {stages.length > 0 && (
        <section>
          <Flex className="rotation-season-heading" align="center" gap={6}>
            <Typography.Title level={5}>{t('Typical season')}</Typography.Title>
            <Tooltip
              title={t(calendarKindLabels[candidate.calendar.kind] ?? candidate.calendar.kind)}
              trigger={['hover', 'focus', 'click']}
            >
              <Button
                type="text"
                size="small"
                shape="circle"
                icon={<CircleHelp size={16} />}
                aria-label={t('About {{label}}', { label: t('Typical season') })}
              />
            </Tooltip>
          </Flex>
          <ol className="rotation-stages" role="list">
            {stages.map(({ stage, day, dateYear }) => (
              <li key={stage}>
                <Typography.Text type="secondary">{t(stageLabels[stage] ?? stage)}</Typography.Text>
                <Typography.Text strong>{formatDayOfYear(day, dateYear, language)}</Typography.Text>
              </li>
            ))}
          </ol>
        </section>
      )}
      {timing && cropTiming && <LocalTiming timing={timing} crop={cropTiming} year={year} />}
      {candidate.soil.length > 0 && <SoilEffects indicators={candidate.soil} />}
      <InformationGaps title={t('Information gaps for this crop')} gaps={candidate.dataGaps} />
    </div>
  );
}
