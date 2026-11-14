import type {
  RotationAdvice,
  RotationCandidate,
  RotationDataGap,
  RotationFinding,
} from '../../../types/rotation/rotation.types.ts';
import { valueLabels } from '../constants/rotationLabels.ts';

type Translate = (key: string, options?: Record<string, unknown>) => string;

export function rankedCandidates(advice: RotationAdvice): RotationCandidate[] {
  return [...advice.candidates].sort((left, right) => left.rank - right.rank);
}

export function seasonYear(advice: RotationAdvice): number {
  return Number(advice.asOf.slice(0, 4));
}

export function dayOfYearDate(day: number, year: number): Date {
  return new Date(Date.UTC(year, 0, day));
}

export function formatDayOfYear(day: number, year: number, language: string): string {
  return new Intl.DateTimeFormat(language, {
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  }).format(dayOfYearDate(day, year));
}

export function formatIsoDay(value: string, language: string): string {
  return new Intl.DateTimeFormat(language, {
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(`${value}T00:00:00Z`));
}

export function formatNumber(value: number, language: string, digits = 1): string {
  return new Intl.NumberFormat(language, { maximumFractionDigits: digits }).format(value);
}

export function formatPercent(value: number, language: string): string {
  return new Intl.NumberFormat(language, { style: 'percent', maximumFractionDigits: 0 }).format(
    value,
  );
}

export function formatUsd(value: number, language: string): string {
  return new Intl.NumberFormat(language, {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value);
}

/** A fact or indicator value in words: known codes are translated, crops use their label. */
export function formatValue(
  value: unknown,
  t: Translate,
  language: string,
  cropLabels: Record<string, string> = {},
): string {
  if (value === null || value === undefined) {
    return t('not known');
  }
  if (Array.isArray(value)) {
    return value.map((item) => formatValue(item, t, language, cropLabels)).join(', ');
  }
  if (typeof value === 'number') {
    return formatNumber(value, language, 2);
  }
  const text = String(value);
  if (cropLabels[text]) {
    return t(cropLabels[text]);
  }
  if (valueLabels[text]) {
    return t(valueLabels[text]);
  }

  return text.replaceAll('_', ' ');
}

/** One entry per gap code, in the order the engine reported them. */
export function distinctGapCodes(gaps: RotationDataGap[]): string[] {
  return [...new Set(gaps.map((gap) => gap.code))];
}

export function sortedFindings(findings: RotationFinding[]): RotationFinding[] {
  return [...findings].sort((left, right) => Math.abs(right.points) - Math.abs(left.points));
}

export function highestRiskLevel(candidate: RotationCandidate): 'low' | 'medium' | 'high' | null {
  const order = ['high', 'medium', 'low'] as const;

  return order.find((level) => candidate.risks.some((risk) => risk.level === level)) ?? null;
}

export function cropLabelMap(advice: RotationAdvice): Record<string, string> {
  return Object.fromEntries(advice.cropOptions.map((option) => [option.id, option.label]));
}
