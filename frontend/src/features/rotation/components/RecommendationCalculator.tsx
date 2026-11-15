import { Card, Skeleton, Typography } from 'antd';
import {
  BrainCircuit,
  Calculator,
  Check,
  CircleDollarSign,
  Droplets,
  Mountain,
  RotateCcw,
  Sprout,
} from 'lucide-react';
import {
  type CSSProperties,
  type ReactNode,
  useEffect,
  useEffectEvent,
  useId,
  useRef,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';
import { CropIcon } from '../../../components/common/CropIcon';
import type {
  RotationAdvice,
  RotationPlanner,
  RotationPriority,
} from '../../../types/rotation/rotation.types.ts';
import { plannerOptions, priorityOptions, sourceKindLabels } from '../constants/rotationLabels.ts';
import { DEFAULT_PLAN_SEASONS, SEASON_CHOICES } from '../utils/planPresentation.ts';
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

const plannerIcons = { exact: Calculator, learned: BrainCircuit };

type RecommendationCalculatorProps = {
  advice: RotationAdvice;
  selectedCrop: string | undefined;
  selectedSeasons: number | undefined;
  selectedPlanner: RotationPlanner;
  priorities: RotationPriority[];
  isUpdating: boolean;
  onCropChange: (crop: string) => void;
  onSeasonsChange: (seasons: number) => void;
  onPlannerChange: (planner: RotationPlanner) => void;
  onPriorityToggle: (priority: RotationPriority, selected: boolean) => void;
};

export function RecommendationCalculator({
  advice,
  selectedCrop,
  selectedSeasons,
  selectedPlanner,
  priorities,
  isUpdating,
  onCropChange,
  onSeasonsChange,
  onPlannerChange,
  onPriorityToggle,
}: RecommendationCalculatorProps) {
  const { t } = useTranslation();
  const cropGroup = useId();
  const plannerGroup = useId();
  const plannerTitle = t('How to build the plan');
  // Offered only when the server has a trained policy to plan with.
  const offerPlanner = advice.plan?.planner?.learnedAvailable === true;
  const cropTitle = t('Choose the crop you plan to grow');
  const goalTitle = t('Select your goals for this season');
  const seasonsTitle = t('Seasons to plan');
  const seasons = selectedSeasons ?? advice.plan?.seasons ?? DEFAULT_PLAN_SEASONS;
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
      <CalculatorStep number={3} title={seasonsTitle}>
        <SeasonSlider
          label={seasonsTitle}
          seasons={seasons}
          firstSeason={advice.plan?.firstSeason ?? null}
          onChange={onSeasonsChange}
        />
      </CalculatorStep>
      {offerPlanner && (
        <CalculatorStep number={4} title={plannerTitle}>
          <fieldset
            className="rotation-option-grid rotation-planner-grid"
            aria-label={plannerTitle}
          >
            {plannerOptions.map((option) => {
              const Icon = plannerIcons[option.value];

              return (
                <label className="rotation-option" key={option.value}>
                  <input
                    type="radio"
                    name={plannerGroup}
                    value={option.value}
                    checked={selectedPlanner === option.value}
                    onChange={() => onPlannerChange(option.value)}
                  />
                  <Icon className="rotation-goal-icon" size={28} aria-hidden="true" />
                  <span>
                    <strong>{t(option.label)}</strong>
                    <br />
                    {t(option.description)}
                  </span>
                  <Check className="rotation-option-check" size={16} aria-hidden="true" />
                </label>
              );
            })}
          </fieldset>
          <Typography.Text type="secondary" className="rotation-calculator-note">
            {t('Both use the same yields, prices, costs and rotation rules of this field.')}
          </Typography.Text>
        </CalculatorStep>
      )}
      <CalculatorStep number={offerPlanner ? 5 : 4} title={t('Crop leaderboard')}>
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

const minSeasons = SEASON_CHOICES[0];
const maxSeasons = SEASON_CHOICES[SEASON_CHOICES.length - 1];
const seasonColors = ['#9bad86', '#88a46e', '#6d9155', '#527a43', '#386333'];

type SeasonSliderProps = {
  label: string;
  seasons: number;
  firstSeason: number | null;
  onChange: (seasons: number) => void;
};

function SeasonSlider({ label, seasons, firstSeason, onChange }: SeasonSliderProps) {
  const { t } = useTranslation();
  const descriptionId = useId();
  const input = useRef<HTMLInputElement>(null);
  const [draft, setDraft] = useState<number | null>(null);
  const value = draft ?? seasons;
  const progress = ((value - minSeasons) / (maxSeasons - minSeasons)) * 100;
  const seasonCount = (count: number) => t('{{count}} seasons', { count });
  function commit(next: number) {
    setDraft(null);
    if (next !== seasons) {
      onChange(next);
    }
  }

  const commitSlider = useEffectEvent((control: HTMLInputElement) => commit(control.valueAsNumber));
  useEffect(() => {
    const control = input.current;
    if (!control) {
      return;
    }
    // The native change event commits a drag once. Input events update the preview.
    const finish = () => commitSlider(control);
    control.addEventListener('change', finish);
    return () => control.removeEventListener('change', finish);
  }, []);

  let years;
  if (firstSeason != null) {
    years = value === 1 ? String(firstSeason) : `${firstSeason}–${firstSeason + value - 1}`;
  }

  return (
    <div
      className="rotation-season-slider"
      style={
        {
          '--rotation-season-fill': `${progress}%`,
          '--rotation-season-color': seasonColors[value - minSeasons],
        } as CSSProperties
      }
    >
      <div className="rotation-season-slider-summary">
        <strong>{seasonCount(value)}</strong>
        {years && <span>{years}</span>}
      </div>
      <div className="rotation-season-track">
        <input
          ref={input}
          type="range"
          aria-label={label}
          aria-describedby={descriptionId}
          aria-valuetext={seasonCount(value)}
          min={minSeasons}
          max={maxSeasons}
          step={1}
          value={value}
          onChange={(event) => setDraft(event.currentTarget.valueAsNumber)}
        />
      </div>
      <div className="rotation-season-options" role="group" aria-label={label}>
        {SEASON_CHOICES.map((season) => (
          <button
            key={season}
            type="button"
            aria-pressed={season === value}
            onClick={() => commit(season)}
          >
            {firstSeason == null
              ? seasonCount(season)
              : t('Through {{year}}', { year: firstSeason + season - 1 })}
          </button>
        ))}
      </div>
      <Typography.Text type="secondary" id={descriptionId} className="rotation-calculator-note">
        {t('The planner compares crop rotations over the number of seasons you choose.')}
      </Typography.Text>
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
