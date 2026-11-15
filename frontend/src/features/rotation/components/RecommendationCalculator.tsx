import { Card, Select, Skeleton, Typography } from 'antd';
import { Check, CircleDollarSign, Droplets, Mountain, RotateCcw, Sprout } from 'lucide-react';
import { type ReactNode, useId } from 'react';
import { useTranslation } from 'react-i18next';
import { CropIcon } from '../../../components/common/CropIcon';
import type { RotationAdvice, RotationPriority } from '../../../types/rotation/rotation.types.ts';
import { priorityOptions, sourceKindLabels } from '../constants/rotationLabels.ts';
import { pricedPlan, SEASON_CHOICES } from '../utils/planPresentation.ts';
import { AdviceVerdict } from './AdviceVerdict';
import { CandidateList } from './CandidateList';
import './RecommendationCalculator.css';

const goalIcons = {
  income: CircleDollarSign,
  soil: Sprout,
  water: Droplets,
  erosion: Mountain,
  pest_break: RotateCcw,
};

type RecommendationCalculatorProps = {
  advice: RotationAdvice;
  selectedCrop: string | undefined;
  priorities: RotationPriority[];
  isUpdating: boolean;
  onCropChange: (crop: string) => void;
  onSeasonsChange?: (seasons: number) => void;
  onPriorityToggle: (priority: RotationPriority, selected: boolean) => void;
};

export function RecommendationCalculator({
  advice,
  selectedCrop,
  priorities,
  isUpdating,
  onCropChange,
  onSeasonsChange,
  onPriorityToggle,
}: RecommendationCalculatorProps) {
  const { t } = useTranslation();
  const cropGroup = useId();
  const cropTitle = t('Choose the crop you plan to grow');
  const goalTitle = t('Select your goals for this season');
  const plan = pricedPlan(advice);
  const crop = isUpdating ? (selectedCrop ?? advice.intendedCrop) : advice.intendedCrop;

  return (
    <div className="rotation-calculator">
      <CalculatorStep number={1} title={cropTitle}>
        <fieldset className="rotation-option-grid" aria-label={cropTitle}>
          {advice.cropOptions.map((option) => (
            <label className="rotation-option" key={option.id}>
              <input
                type="radio"
                name={cropGroup}
                value={option.id}
                checked={crop === option.id}
                onChange={() => onCropChange(option.id)}
              />
              <CropIcon crop={option.label} size={40} />
              <span>{t(option.label)}</span>
              <Check className="rotation-option-check" size={16} aria-hidden="true" />
            </label>
          ))}
        </fieldset>
        {crop === advice.intendedCrop && advice.intendedCropSource !== 'requested' && (
          <Typography.Text type="secondary" className="rotation-calculator-note">
            {t('Starting point: {{source}}.', {
              source: t(sourceKindLabels[advice.intendedCropSource]),
            })}
          </Typography.Text>
        )}
        {!isUpdating && <AdviceVerdict advice={advice} />}
      </CalculatorStep>
      <CalculatorStep number={2} title={goalTitle}>
        <fieldset className="rotation-option-grid" aria-label={goalTitle}>
          {priorityOptions.map((option) => {
            const Icon = goalIcons[option.value];

            return (
              <label className="rotation-option" key={option.value}>
                <input
                  type="checkbox"
                  checked={priorities.includes(option.value)}
                  onChange={(event) => onPriorityToggle(option.value, event.target.checked)}
                />
                <Icon className="rotation-goal-icon" size={28} aria-hidden="true" />
                <span>{t(option.label)}</span>
                <Check className="rotation-option-check" size={16} aria-hidden="true" />
              </label>
            );
          })}
        </fieldset>
        <Typography.Text type="secondary" className="rotation-calculator-note">
          {t('Risks and benefits in the areas you pick count double.')}
        </Typography.Text>
      </CalculatorStep>
      <CalculatorStep number={3} title={t('Crop leaderboard')}>
        {plan && onSeasonsChange && (
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
        <div aria-busy={isUpdating}>
          {isUpdating ? (
            <Skeleton active title={false} paragraph={{ rows: 4 }} />
          ) : (
            <CandidateList advice={advice} />
          )}
        </div>
      </CalculatorStep>
    </div>
  );
}

type CalculatorStepProps = { number: number; title: string; children: ReactNode };

function CalculatorStep({ number, title, children }: CalculatorStepProps) {
  return (
    <Card className="rotation-calculator-step">
      <Typography.Title level={2} className="rotation-calculator-title">
        <span className="rotation-step-number">{number}</span>
        {title}
      </Typography.Title>
      {children}
    </Card>
  );
}
