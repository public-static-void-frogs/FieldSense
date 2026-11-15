import { Card, Tag, Tooltip, Typography } from 'antd';
import { CircleHelp, Satellite } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { CropIcon } from '../../../components/common/CropIcon';
import type { RotationAdvice } from '../../../types/rotation/rotation.types.ts';
import { catalogCropLabels } from '../constants/rotationLabels.ts';
import { cropLabelMap, seasonYear } from '../utils/rotationPresentation.ts';
import './CropHistoryStrip.css';

type CropHistoryStripProps = { advice: RotationAdvice };

export function CropHistoryStrip({ advice }: CropHistoryStripProps) {
  const { t } = useTranslation();
  const { historySource, history } = advice;

  return (
    <Card
      className="rotation-history"
      title={t('What grew here')}
      extra={
        historySource.satelliteEstimate && (
          <Tag icon={<Satellite size={14} aria-hidden="true" />} className="rotation-estimate-tag">
            {(historySource.declaredSeasons ?? 0) > 0
              ? t('Satellite estimate and your records')
              : t('Satellite estimate')}
          </Tag>
        )
      }
    >
      <CropHistoryTimeline advice={advice} />
      {history.length === 0 && (
        <Typography.Paragraph type="secondary" className="rotation-history-note">
          {t('No crop history is known for this field, so rotation rules could not be checked.')}
        </Typography.Paragraph>
      )}
      {historySource.satelliteEstimate && (
        <Typography.Paragraph type="secondary" className="rotation-history-note">
          {t(
            'Crops are read from USDA satellite maps (Cropland Data Layer). They are estimates, not your own records, and can be wrong for a single year.',
          )}
        </Typography.Paragraph>
      )}
      {historySource.kind === 'declared' && (
        <Typography.Paragraph type="secondary" className="rotation-history-note">
          {t('Only the crop recorded for this field is known; earlier years are missing.')}
        </Typography.Paragraph>
      )}
    </Card>
  );
}

const recentSeasons = 5;

function CropHistoryTimeline({ advice }: CropHistoryStripProps) {
  const { t } = useTranslation();
  const labels = cropLabelMap(advice);
  const historyByYear = new Map(advice.history.map((entry) => [entry.year, entry]));
  const recordedYears = [...historyByYear.keys()];
  const year = seasonYear(advice);
  const firstYear = Math.min(year - recentSeasons, ...recordedYears);
  const lastYear = Math.max(year - 1, ...recordedYears);
  const years = Array.from({ length: lastYear - firstYear + 1 }, (_, index) => firstYear + index);

  return (
    <ol className="rotation-history-timeline" role="list" aria-label={t('Crop history')}>
      {years.map((year) => {
        const entry = historyByYear.get(year);
        const crop = entry?.crop;
        const cropLabel =
          crop && (labels[crop] ?? historyCropLabels[crop] ?? catalogCropLabels[crop] ?? crop);
        const name = cropLabel ? t(cropLabel) : t('Unknown crop');
        let source;
        if (!cropLabel) {
          source = t('No crop record for this year.');
        } else if (entry?.source === 'cdl') {
          source = t('Satellite estimate');
        } else if (entry?.source === 'declared') {
          source = t('Crop recorded on this field');
        }

        return (
          <Tooltip
            key={year}
            trigger={['hover', 'focus', 'click']}
            title={
              <>
                <strong>
                  {year} · {name}
                </strong>
                {source && <div>{source}</div>}
              </>
            }
          >
            <li className="rotation-history-season" data-unknown={!cropLabel} tabIndex={0}>
              <time dateTime={String(year)}>{year}</time>
              <div className="rotation-history-track" aria-hidden="true" />
              <div className="rotation-history-crop">
                {cropLabel ? (
                  <CropIcon crop={entry?.cdlCode ?? cropLabel} size={32} />
                ) : (
                  <CircleHelp size={24} aria-hidden="true" />
                )}
                <span>{name}</span>
              </div>
            </li>
          </Tooltip>
        );
      })}
    </ol>
  );
}

// Crops that can appear in history without being a candidate in the state.
const historyCropLabels: Record<string, string> = {
  corn: 'Corn (grain)',
  sorghum: 'Sorghum (grain)',
  soybeans: 'Soybeans',
  oats: 'Oats',
  winter_wheat: 'Winter wheat',
  spring_wheat: 'Spring wheat',
  rye: 'Rye (grain)',
  barley: 'Barley',
  alfalfa: 'Alfalfa',
  other_hay: 'Other hay (non-alfalfa)',
  grass_pasture: 'Grassland or pasture',
  dry_beans: 'Dry beans',
  canola: 'Canola',
  sunflower: 'Sunflower',
  fallow: 'Fallow or idle cropland',
  double_crop_winter_wheat_soybeans: 'Double crop winter wheat / soybeans',
  non_crop: 'Not cropland',
};
