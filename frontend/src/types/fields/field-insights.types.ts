import type { CropHistoryPoint } from './crop-history.types.ts';

export type SoilSignal = 'rotation' | 'greenness' | 'soil' | 'county';

export type SoilAssessment = {
  score: number | null;
  level: 'low' | 'moderate' | 'high' | 'very_high' | 'unknown';
  coverage: number;
  components: Record<SoilSignal, number | null>;
  drivers: SoilSignal[];
  metrics: {
    years_same_crop: number | null;
    latest_crop: string | null;
    top_crop_5y: string | null;
    share_top_crop_5y: number | null;
    observed_years_5y: number | null;
    peak_ndvi: Record<string, number> | null;
    peak_evi: Record<string, number> | null;
    ndvi_trend_pct_per_yr: number | null;
    om_pct_0_30cm: number | null;
    aws0150_cm: number | null;
    slope_pct: number | null;
    county_yield_ratio_mean: number | null;
    county_yield_ratio_slope_pct_yr: number | null;
  };
  notes: string[];
};

export type SoilDepletion = {
  status: 'pending' | 'busy' | 'ready';
  coordinates: CropHistoryPoint;
  assessment: SoilAssessment | null;
};

export type M3Crop = 'corn' | 'soybeans';
export type M3Scenario = 'ssp245' | 'ssp585';

export type M3Window = {
  date_q10: string | null;
  date_q50: string | null;
  date_q90: string | null;
  n_years_fit: number | null;
  calibrated: boolean | null;
  censored_share: number | null;
};

export type M3FutureWindow = {
  date_q50_median: string | null;
  date_q50_min: string | null;
  date_q50_max: string | null;
  n_models: number;
};

export type M3CurrentRisk = {
  n_years: number | null;
  p_heat_overlap: number | null;
  p_heat_lo80: number | null;
  p_heat_hi80: number | null;
  p_frost_before_maturity: number | null;
  adaptation_margin_days: number | null;
  workable_days_q50: number | null;
};

export type M3FutureRisk = {
  p_heat_median: number | null;
  p_heat_min: number | null;
  p_heat_max: number | null;
  margin_min: number | null;
  margin_max: number | null;
  n_models: number;
};

type M3WaterBranch = {
  paw_sow_mm: { q50: number | null };
  p_shortfall: number | null;
  safe_autumn_rain_mm: number | null;
};

export type M3Water = {
  bare?: M3WaterBranch;
  cover?: M3WaterBranch;
  cover_ok?: boolean | null;
};

export type M3Delay = { delay_days: number; p_heat: number | null; p_frost: number | null };

export type M3Insights = {
  ok: boolean;
  match: {
    level: 'field' | 'cell';
    distance_km: number;
    awc_mm: number | null;
  } | null;
  windows: {
    now: Record<string, M3Window>;
    future: Partial<Record<M3Scenario, Record<string, M3FutureWindow>>>;
  } | null;
  risk: {
    now: Partial<Record<M3Crop, M3CurrentRisk>>;
    future: Partial<Record<M3Scenario, Partial<Record<M3Crop, M3FutureRisk>>>>;
  } | null;
  delay_scan: { now?: { obs?: Partial<Record<M3Crop, M3Delay[]>> } } | null;
  fallow_zero: Partial<Record<'after_corn' | 'after_soybeans', M3Water>> | null;
  meta: { nass_validation_mae_days: Partial<Record<M3Crop, { planted?: number }>> | null } | null;
  warnings: string[];
  error: { code: 'outside_coverage' | 'bad_input'; nearest_cell_km: number | null } | null;
};
