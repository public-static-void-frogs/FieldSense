import type {
  RotationAdvice,
  RotationCandidate,
  RotationPlan,
  RotationPlanCrop,
} from '../../../types/rotation/rotation.types.ts';

export const SEASON_CHOICES = [1, 2, 3, 4, 5];
export const DEFAULT_PLAN_SEASONS = 3;

/** The plan when the solver could price at least one crop. */
export function pricedPlan(advice: RotationAdvice): RotationPlan | null {
  return advice.plan?.status === 'ok' && advice.plan.crops.length > 0 ? advice.plan : null;
}

export function planCrop(advice: RotationAdvice, crop: string): RotationPlanCrop | undefined {
  return pricedPlan(advice)?.crops.find((entry) => entry.crop === crop);
}

export function rankedPlanCrops(plan: RotationPlan): RotationPlanCrop[] {
  return [...plan.crops].sort((left, right) => left.rank - right.rank);
}

/** Candidates the solver had no cost budget or yield for; they keep their rotation-risk order. */
export function unpricedCandidates(
  advice: RotationAdvice,
  plan: RotationPlan,
): RotationCandidate[] {
  const priced = new Set(plan.crops.map(({ crop }) => crop));

  return advice.candidates
    .filter(({ crop }) => !priced.has(crop))
    .sort((left, right) => left.rank - right.rank);
}

export function lastSeason(plan: RotationPlan): number | null {
  return plan.firstSeason === null ? null : plan.firstSeason + plan.seasons - 1;
}

export function formatSignedUsd(value: number, language: string): string {
  return new Intl.NumberFormat(language, {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
    signDisplay: 'negative',
  }).format(value);
}

export function parseSeasons(value: string | null): number | undefined {
  const seasons = Number(value);

  return SEASON_CHOICES.includes(seasons) ? seasons : undefined;
}

/** A crop id in words: its catalog label when the state lists it, else the id spelled out. */
export function cropNamer(advice: RotationAdvice): (crop: string) => string {
  const labels = Object.fromEntries(advice.cropOptions.map(({ id, label }) => [id, label]));

  return (crop) => labels[crop] ?? crop.replaceAll('_', ' ');
}
