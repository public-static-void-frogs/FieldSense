import { Card, Flex, Tag, Typography } from 'antd';
import { Satellite } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { RotationAdvice } from '../../../types/rotation/rotation.types.ts';
import { cropLabelMap } from '../utils/rotationPresentation.ts';

type CropHistoryStripProps = { advice: RotationAdvice };

export function CropHistoryStrip({ advice }: CropHistoryStripProps) {
  const { t } = useTranslation();
  const labels = cropLabelMap(advice);
  const { historySource, history } = advice;
  const cropName = (crop: string | null) => {
    if (!crop) {
      return t('Other land cover');
    }

    return t(labels[crop] ?? historyCropLabels[crop] ?? crop);
  };

  return (
    <Card
      className="rotation-history"
      title={t('What grew here')}
      extra={
        historySource.satelliteEstimate && (
          <Tag icon={<Satellite size={14} aria-hidden="true" />} className="rotation-estimate-tag">
            {t('Satellite estimate')}
          </Tag>
        )
      }
    >
      {history.length === 0 ? (
        <Typography.Paragraph type="secondary">
          {t('No crop history is known for this field, so rotation rules could not be checked.')}
        </Typography.Paragraph>
      ) : (
        <Flex gap={10} wrap component="ol" className="rotation-history-years">
          {history.map((entry) => (
            <li key={entry.year} className="rotation-history-year">
              <Typography.Text type="secondary">{entry.year}</Typography.Text>
              <Typography.Text strong>{cropName(entry.crop)}</Typography.Text>
            </li>
          ))}
        </Flex>
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
