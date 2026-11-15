import type { M2Outcome } from '../../../types/fields/field-insights.types.ts';

export function m2Range(headline: M2Outcome) {
  const drought = headline.gamma != null;
  const estimate = drought ? headline.gamma : headline.headline_effect;
  const low = drought ? headline.gamma_lo : headline.headline_lo;
  const high = drought ? headline.gamma_hi : headline.headline_hi;
  if (estimate == null || !Number.isFinite(estimate)) {
    return null;
  }

  const interval =
    low != null && high != null && Number.isFinite(low) && Number.isFinite(high) && low <= high
      ? { low, high }
      : null;
  const normalGap =
    drought && headline.theta_normal != null && Number.isFinite(headline.theta_normal)
      ? headline.theta_normal
      : null;
  // Outcomes use different units, so each row shows its own scale centred on zero.
  const limit = Math.max(
    Math.abs(estimate),
    Math.abs(interval?.low ?? 0),
    Math.abs(interval?.high ?? 0),
    Math.abs(normalGap ?? 0),
  );
  const position = (value: number) => (limit === 0 ? 50 : 50 + (value / limit) * 50);

  return { estimate, interval, normalGap, limit, position };
}
