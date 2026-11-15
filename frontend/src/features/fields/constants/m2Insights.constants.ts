export const m2Crops = { corn: 'Corn', soybeans: 'Soybeans' } as const;
export const m2Treatments = {
  T1: 'Continuous cropping',
  T2: 'Diverse rotation (3+ crop groups in 5 years)',
  T3: 'Small grain or hay in the last 3 years',
  T4: 'Winter cover crop',
  T5: 'Host-crop return interval of 2+ years',
} as const;
export const m2Outcomes = {
  peak_ndvi: 'Peak greenness (NDVI)',
  ndwi_jul_aug: 'July–August water content (NDWI)',
  late_ndvi: 'Late-season greenness (NDVI)',
  ndvi_area: 'Seasonal greenness (NDVI × days)',
} as const;
export const m2Tiers = {
  limited: 'Small sample',
  'one season type': 'One season type only',
  pooled: 'All seasons pooled',
  descriptive: 'Descriptive only',
} as const;
export const m2Verdicts: Record<
  string,
  { label: string; tone: 'success' | 'warning' | 'default' }
> = {
  'supported (all checks pass)': { label: 'Supported by the data', tone: 'success' },
  'supported by the DML model; matched baseline not fully balanced': {
    label: 'Supported by the model only',
    tone: 'warning',
  },
  'interval excludes 0, but placebo or negative control fails': {
    label: 'Not reliable: validation checks failed',
    tone: 'warning',
  },
  'no detectable drought-specific effect': { label: 'No drought effect detected', tone: 'default' },
  'arm gap only (drought effect not identified)': {
    label: 'Gap between practices only',
    tone: 'default',
  },
  abstain: { label: 'Not enough data', tone: 'default' },
};
