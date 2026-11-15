export function formatPercent(value: number | null | undefined, fallback: string) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return fallback;
  }

  return `${value}%`;
}
export function positiveSign(value: number) {
  return value > 0 ? '+' : '';
}
