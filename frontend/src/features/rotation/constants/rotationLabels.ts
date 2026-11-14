import type { RotationPriority } from '../../../types/rotation/rotation.types.ts';

// Engine codes -> English catalog keys. Unknown codes are shown as they arrive.

export const priorityOptions: { value: RotationPriority; label: string }[] = [
  { value: 'income', label: 'Income' },
  { value: 'soil', label: 'Soil health' },
  { value: 'water', label: 'Water' },
  { value: 'erosion', label: 'Erosion control' },
  { value: 'pest_break', label: 'Pest and disease break' },
];

export const categoryLabels: Record<string, string> = {
  diversity: 'Rotation diversity',
  erosion: 'Erosion',
  soil_nutrient: 'Soil and nutrients',
  temperature: 'Temperature',
  water: 'Water',
  pest_disease: 'Pests and diseases',
  yield: 'Yield',
  market: 'Market',
  herbicide: 'Herbicides',
  cover_crop: 'Cover crops',
  tillage: 'Tillage',
};

export const levelLabels: Record<string, string> = {
  low: 'Low risk',
  medium: 'Medium risk',
  high: 'High risk',
};

export const levelColors: Record<string, string> = {
  low: 'gold',
  medium: 'orange',
  high: 'red',
};

export const evidenceLabels: Record<string, string> = {
  strong: 'Strong evidence',
  moderate: 'Moderate evidence',
  weak: 'Limited evidence',
};

export const stageLabels: Record<string, string> = {
  planted: 'Planting',
  emerged: 'Emergence',
  flowering: 'Flowering',
  grain_fill: 'Grain fill',
  mature: 'Maturity',
  harvested: 'Harvest',
};

export const calendarKindLabels: Record<string, string> = {
  nass_region: 'Typical dates from USDA crop progress reports for this state',
  nass: 'Typical dates from USDA crop progress reports for this state',
  crop_default: 'Typical dates for this crop, not specific to this state',
  group_default: 'Approximate dates for this crop group, not specific to this state',
};

export const metricLabels: Record<string, string> = {
  tmax_ge35_days: 'days at 35 °C (95 °F) or hotter',
  tmax_ge30_days: 'days at 30 °C (86 °F) or hotter',
  pr_ge25_days: 'days with 25 mm (1 in) of rain or more',
  tmin_min: 'lowest night temperature, °C',
  dm_max: 'worst Drought Monitor class (0 = D0 … 4 = D4)',
  rz_lt20_days: 'days with very dry root-zone soil',
};

export const factLabels: Record<string, string> = {
  'candidate.bare_soil_months': 'Months of bare soil under this crop',
  'candidate.crop': 'Crop',
  'candidate.humus_balance': 'Organic-matter balance of this crop',
  'candidate.lifecycle': 'Crop life cycle',
  'candidate.min_return_years': 'Recommended years before this crop returns',
  'candidate.n_demand': 'Nitrogen demand of this crop',
  'candidate.water_demand': 'Water demand of this crop',
  'county.rma_drought_share_lag1': 'Share of county crop-insurance losses from drought last year',
  'county.rma_excess_moisture_share_lag1':
    'Share of county crop-insurance losses from excess moisture last year',
  'field.practice.cover_crop': 'Cover crop',
  'field.practice.cover_planned': 'Cover crop planned',
  'field.practice.cover_termination_days': 'Days between cover-crop termination and planting',
  'field.practice.tillage': 'Tillage',
  'field.practice.weed_escapes': 'Weed escapes reported',
  'field.soil.aws_100cm_mm': 'Water the top metre of soil can hold, mm',
  'field.soil.caco3_pct': 'Soil carbonate, %',
  'field.soil.hel': 'Highly erodible land',
  'field.soil.nirr_class': 'Land capability class',
  'field.soil.ph': 'Soil pH',
  'field.soil.sand_pct': 'Sand, %',
  'field.soil.slope_pct': 'Slope, %',
  'field.soil.wetness': 'Soil drainage',
  'herbicide.late_restricted_count': 'Late residual herbicide applications',
  'herbicide.repeated_group_count': 'Herbicide groups repeated two seasons running',
  'herbicide.restricted_actives': 'Herbicides with an unmet plant-back interval',
  'herbicide.shortfall_months': 'Months short of the plant-back interval',
  'history.candidate_group_in_5y': 'Same crop group grown in the last five years',
  'history.consecutive_same_crop': 'Years in a row of this crop',
  'history.consecutive_same_family': 'Years in a row of this crop family',
  'history.corn_soy_alternation_years': 'Years of strict corn-soybean alternation',
  'history.distinct_groups_5y': 'Different crop groups in the last five years',
  'history.prev1.crop': 'Last year’s crop',
  'history.prev1.group': 'Last year’s crop group',
  'history.prev1.humus_balance': 'Organic-matter balance of last year’s crop',
  'history.prev1.n_demand': 'Nitrogen demand of last year’s crop',
  'history.prev1.n_fixer': 'Last year’s crop fixed nitrogen',
  'history.share_same_crop_5y': 'Share of the last five years under this crop',
  'history.shared_hosts_prev1': 'Diseases shared with last year’s crop',
  'history.years': 'Years of crop history known',
  'history.years_since_same_family': 'Years since this crop family was grown',
};

export const gapLabels: Record<string, string> = {
  no_csb_id:
    'This field is not linked to a mapped USDA field, so weather history and county yields are not used.',
  no_season_summary:
    'No drought and soil moisture history is loaded for this field, so drought risks were not checked.',
  no_weather_record:
    'No long weather record covers this location, so weather risks were counted over few seasons or not at all.',
  few_weather_seasons: 'Only a few seasons of weather history are available for this field.',
  short_history: 'Fewer years of crop history than the rotation rules need.',
  soil_not_provided: 'Some soil facts are missing, so the rules that need them stayed silent.',
  practices_not_provided:
    'Tillage, cover crops and herbicides were not provided, so the rules that need them stayed silent.',
  region_not_supported:
    'This state has no crop list yet; the Iowa crop list and dates are used instead.',
  rule_uses_unverified_traits: 'A rule relies on crop values that still need expert review.',
  calendar_not_nass: 'Growth-stage dates are approximate, not from this state’s crop reports.',
  no_yield_estimate: 'No yield estimate is available for this crop here.',
  price_not_local: 'The price is not local to this state.',
  hazards_not_evaluated: 'Weather risks were not checked for this crop.',
  hazard_stage_not_in_calendar:
    'A weather rule was skipped because this crop has no date for that growth stage.',
  yield_unverified: 'The yield estimate is not based on local county records.',
  no_price: 'No price is available for this crop.',
};

export const soilIndicatorLabels: Record<string, string> = {
  bare_soil_months: 'Months of bare soil',
  erosion_exposure: 'Erosion exposure factor',
  residue_return: 'Residue returned to the soil',
  humus_balance: 'Organic-matter balance',
  n_balance: 'Nitrogen',
  rotation_diversity: 'Different crops in five years',
  rootzone_dry_weeks: 'Dry root-zone weeks last season',
};

export const valueLabels: Record<string, string> = {
  wet: 'Poorly drained',
  somewhat_wet: 'Somewhat poorly drained',
  not_wet: 'Well drained',
  tiled: 'Tile drained',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
  fixes_n: 'Fixes its own nitrogen',
  low_demand: 'Low demand',
  medium_demand: 'Medium demand',
  high_demand: 'High demand',
  credit_from_previous_legume: 'Credit from last year’s legume',
  annual: 'Annual',
  perennial: 'Perennial',
  winter_annual: 'Winter annual',
  true: 'Yes',
  false: 'No',
};

export const sourceKindLabels: Record<string, string> = {
  requested: 'the crop you chose',
  field_crop: 'the crop recorded for this field',
  history: 'the most recent crop seen from satellite',
  default: 'the main crop of this state',
};
