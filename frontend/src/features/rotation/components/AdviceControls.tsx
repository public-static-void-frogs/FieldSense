import { Card, Flex, Select, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import type { RotationAdvice, RotationPriority } from '../../../types/rotation/rotation.types.ts';
import { priorityOptions, sourceKindLabels } from '../constants/rotationLabels.ts';
import { pricedPlan, SEASON_CHOICES } from '../utils/planPresentation.ts';

type AdviceControlsProps = {
  advice: RotationAdvice;
  priorities: RotationPriority[];
  onCropChange: (crop: string) => void;
  onSeasonsChange: (seasons: number) => void;
  onPriorityToggle: (priority: RotationPriority, selected: boolean) => void;
};

export function AdviceControls({
  advice,
  priorities,
  onCropChange,
  onSeasonsChange,
  onPriorityToggle,
}: AdviceControlsProps) {
  const { t } = useTranslation();
  const plan = pricedPlan(advice);

  return (
    <Card className="rotation-controls">
      <Flex gap={32} wrap>
        <div className="rotation-control">
          <Typography.Text strong id="rotation-crop-label">
            {t('Crop you plan to grow')}
          </Typography.Text>
          <Select
            aria-labelledby="rotation-crop-label"
            className="rotation-crop-select"
            value={advice.intendedCrop}
            options={advice.cropOptions.map((option) => ({
              value: option.id,
              label: t(option.label),
            }))}
            onChange={onCropChange}
          />
          <Typography.Text type="secondary">
            {t('Starting point: {{source}}.', {
              source: t(sourceKindLabels[advice.intendedCropSource]),
            })}
          </Typography.Text>
        </div>
        {plan && (
          <div className="rotation-control rotation-control-narrow">
            <Typography.Text strong id="rotation-seasons-label">
              {t('Seasons to plan')}
            </Typography.Text>
            <Select
              aria-labelledby="rotation-seasons-label"
              className="rotation-seasons-select"
              value={plan.seasons}
              options={SEASON_CHOICES.map((value) => ({ value, label: String(value) }))}
              onChange={onSeasonsChange}
            />
            <Typography.Text type="secondary">
              {t('First season: {{year}}.', { year: plan.firstSeason })}
            </Typography.Text>
          </div>
        )}
        <div className="rotation-control">
          <Typography.Text strong>{t('What matters most to you')}</Typography.Text>
          <Flex gap={8} wrap role="group" aria-label={t('What matters most to you')}>
            {priorityOptions.map((option) => (
              <Tag.CheckableTag
                key={option.value}
                className="rotation-priority"
                checked={priorities.includes(option.value)}
                onChange={(selected) => onPriorityToggle(option.value, selected)}
              >
                {t(option.label)}
              </Tag.CheckableTag>
            ))}
          </Flex>
          <Typography.Text type="secondary">
            {t('Risks and benefits in the areas you pick count double.')}
          </Typography.Text>
        </div>
      </Flex>
      <Typography.Paragraph className="rotation-scoring-note">
        {plan
          ? t(
              'How plans are ranked: expected result per acre, less a charge for each rotation risk, plus the value of soil carbon gained.',
            )
          : t(
              'How crops are ranked: each risk adds 1 to 3 points by severity and each benefit removes 1. The crop with the fewest points comes first.',
            )}
      </Typography.Paragraph>
    </Card>
  );
}
