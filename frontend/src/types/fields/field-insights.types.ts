import type { CropHistoryPoint } from './crop-history.types.ts';

export type SoilSignal = 'rotation' | 'greenness' | 'soil' | 'county';

export type CropDemandClass = 'high' | 'moderate' | 'low' | 'restorative';
export type CropRepeatMark = 'repeat' | 'heavy_repeat';

export type SoilAssessment = {
  score: number | null;
  level: 'low' | 'moderate' | 'high' | 'very_high' | 'unknown';
  coverage: number;
  components: Record<SoilSignal, number | null>;
  drivers: SoilSignal[];
  metrics: {
    demand_latest_crop: number | null;
    demand_class_latest: CropDemandClass | null;
    latest_repeat_mark: CropRepeatMark | null;
    demand_mean_5y: number | null;
    rotation_repeat: number | null;
    rotation_load: number | null;
    rotation_concentration: number | null;
    rotation_marks: {
      year: number;
      crop: string;
      demand: number;
      demand_class: CropDemandClass;
      run: number;
      mark: CropRepeatMark | null;
    }[];
    unrated_crops: string[];
    latest_ndvi: number | null;
    latest_evi: number | null;
    latest_vs_peak_mean: number | null;
    latest_greenness_date: string | null;
    peak_scene_count: Record<string, number> | null;
    mukey: number | null;
    soil_component: string | null;
    drainage_class: string | null;
    hydrologic_group: string | null;
    kffact: number | null;
    county_fips: string | null;
    county_yield_years: number | null;
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
    reference_awc_mm?: number | null;
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

export type M2Crop = 'corn' | 'soybeans';
export type M2Treatment = 'T1' | 'T2' | 'T3' | 'T4' | 'T5';

export type M2Checks = {
  gamma_placebo_p: number | null;
  neg_control_pass: boolean | null;
  balance_pass: boolean | null;
  few_clusters: boolean | null;
  max_smd_after: number | null;
};

export type M2Outcome = {
  outcome_label: string | null;
  gamma: number | null;
  gamma_lo: number | null;
  gamma_hi: number | null;
  theta_normal: number | null;
  theta_drought: number | null;
  verdict: string | null;
  outcome_sees_drought: boolean | null;
  squares: number | null;
  checks: M2Checks;
};

export type M2Region = {
  treated: string;
  control: string;
  expected_sign: -1 | 1;
  abstain: boolean;
  abstain_reason: string | null;
  verdict: string;
  headline: (M2Outcome & { outcome: string }) | null;
  outcomes: Record<string, M2Outcome>;
};

export type M2FieldEffect = {
  usable: boolean;
  status: string;
  n_comparable_treated: number | null;
  n_comparable_control: number | null;
  effect?: number | null;
  lo95?: number | null;
  hi95?: number | null;
  effect_agrees?: boolean;
};

export type M2NeighbourEffect = {
  n_fields: number;
  n_usable: number;
  median?: number | null;
  p10?: number | null;
  p90?: number | null;
  share_expected_sign?: number | null;
};

type M2ByCrop<T> = Partial<Record<M2Crop, Partial<Record<M2Treatment, Record<string, T>>>>>;

export type M2Insights = {
  ok: boolean;
  evidence_label: string | null;
  match: {
    level: 'field' | 'neighbourhood' | 'region';
    csbid: string | null;
    distance_km: number | null;
    n_neighbour_fields: number | null;
  } | null;
  region: Partial<Record<M2Crop, Partial<Record<M2Treatment, M2Region>>>> | null;
  field: M2ByCrop<M2FieldEffect> | null;
  neighbourhood: M2ByCrop<M2NeighbourEffect> | null;
  summary: string[];
  warnings: string[];
  error: { code: 'outside_coverage' | 'bad_input'; nearest_field_km: number | null } | null;
};
