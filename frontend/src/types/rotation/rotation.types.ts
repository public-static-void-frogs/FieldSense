export type RotationPriority = 'water' | 'soil' | 'erosion' | 'income' | 'pest_break';

export type RotationDataGap = { code: string } & Record<string, unknown>;

export type RotationCondition = {
  fact: string;
  op: string;
  expected: unknown;
  actual: unknown;
};

export type RotationHazardSeason = { year: number; value: number | null; hit: boolean };

export type RotationTrigger =
  | { type: 'conditions'; conditions: RotationCondition[] }
  | {
      type: 'hazard';
      stage: string;
      window: { startDate: string; endDate: string };
      metric: string;
      metricUnit: string;
      compare: string;
      threshold: number;
      seasonsHit: number;
      seasonsTotal: number;
      worstYear: number | null;
      worstValue: number | null;
      perSeason: RotationHazardSeason[];
    };

export type RotationFinding = {
  ruleId: string;
  title: string;
  category: string;
  kind: 'risk' | 'benefit' | 'advisory';
  level: 'low' | 'medium' | 'high' | null;
  points: number;
  yieldFactor: { low: number; high: number } | null;
  evidenceStrength: string | null;
  unverifiedTraits: string[];
  needsLocalReview: boolean;
  trigger: RotationTrigger;
};

export type RotationYield = {
  low: number;
  mid: number;
  high: number;
  unit: string;
  method: string | null;
  level: string | null;
  verified: boolean | null;
};

export type RotationRevenue = {
  lowUsd: number;
  midUsd: number;
  highUsd: number;
  priceUsd: number;
  priceUnit: string;
  priceAsOf: string | null;
  priceLevel: string | null;
  areaHa: number;
  grossOnly: boolean;
};

export type RotationSoilIndicator = {
  id: string;
  value: number | string | null;
  unit: string | null;
  direction: string | null;
  verified: boolean | null;
};

export type RotationCandidate = {
  crop: string;
  label: string;
  group: string;
  rank: number;
  isIntended: boolean;
  score: number;
  economicsAvailable: boolean;
  risks: RotationFinding[];
  benefits: RotationFinding[];
  advisories: RotationFinding[];
  calendar: {
    kind: string;
    stages: Record<string, number | null>;
    localShiftDays: Record<string, number>;
    localSource: string | null;
  };
  soil: RotationSoilIndicator[];
  yield: RotationYield | null;
  revenue: RotationRevenue | null;
  dataGaps: RotationDataGap[];
  needsLocalReview: boolean;
};

export type RotationHistoryYear = {
  year: number;
  crop: string | null;
  cdlCode: number | null;
  source: string;
};

export type RotationTimingWindow = {
  early: string;
  typical: string;
  late: string;
  method: string | null;
  yearsFit: number | null;
};

export type RotationCropTiming = {
  stages: Partial<Record<'firstWorkable' | 'sow' | 'flower' | 'mature', RotationTimingWindow>>;
  dateErrorDays: Partial<Record<'sow' | 'flower' | 'mature', number>>;
  heatAtFlowering: {
    probability: number | null;
    low80: number | null;
    high80: number | null;
    meanHotDays: number | null;
    vulnerable: boolean;
  };
  frostBeforeMaturity: number | null;
  sowingDelayMarginDays: number | null;
  workableDays: { low: number | null; typical: number | null; high: number | null };
  years: number | null;
  outlook2040: {
    scenario: 'ssp245' | 'ssp585';
    heatMedian: number | null;
    heatMin: number | null;
    heatMax: number | null;
    marginMinDays: number | null;
    marginMaxDays: number | null;
    models: number | null;
  }[];
};

export type RotationSeasonTiming = {
  source: 'm3';
  matchLevel: 'field' | 'cell';
  distanceKm: number;
  cellId: string;
  lastSpringFrost: RotationTimingWindow | null;
  firstAutumnFrost: RotationTimingWindow | null;
  crops: Record<string, RotationCropTiming>;
  /** Keyed by the crop just harvested. */
  waterAtSowing: Record<string, RotationWaterAtSowing>;
};

export type RotationWaterBranch = {
  shortfall: number | null;
  low80: number | null;
  high80: number | null;
  typicalMm: number | null;
};

export type RotationWaterAtSowing = {
  nextCrop: string;
  years: number | null;
  thresholdMm: number | null;
  bare: RotationWaterBranch;
  cover: RotationWaterBranch;
  coverOk: boolean | null;
  safeAutumnRainMm: number | null;
  autumnRainTypicalMm: number | null;
};

export type RotationAdvice = {
  fieldId: string;
  intendedCrop: string;
  intendedCropSource: 'requested' | 'field_crop' | 'history' | 'default';
  cropOptions: { id: string; label: string; group: string }[];
  region: string;
  asOf: string;
  areaHa: number;
  ruleSetVersion: string;
  units: 'metric' | 'imperial';
  priorities: RotationPriority[];
  historySource: {
    kind: 'cdl' | 'declared' | 'none';
    seasons: number;
    firstYear: number | null;
    lastYear: number | null;
    satelliteEstimate: boolean;
  };
  history: RotationHistoryYear[];
  seasonsAvailable: number[];
  weatherRecord: RotationWeatherRecord | null;
  offSeason: RotationOffSeason | null;
  dataGaps: RotationDataGap[];
  candidates: RotationCandidate[];
  seasonTiming: RotationSeasonTiming | null;
};

export type RotationWeatherRecord = {
  source: string;
  seasons: number;
  firstYear: number;
  lastYear: number;
  nodeLatitude: number;
  nodeLongitude: number;
  distanceKm: number;
};

export type RotationOffSeasonOption = {
  id: string;
  label: string;
  kind: 'cover_crop' | 'winter_cash_crop';
  overwinters: boolean;
  cropId: string | null;
  level: 'reliable' | 'marginal' | 'unlikely';
  seasonsMet: number;
  seasonsTotal: number;
  share: number;
  metric: 'fall_gdd0' | 'days_to_killing_frost';
  minimum: number;
  typical: number;
  needsLocalReview: boolean;
};

export type RotationOffSeason = {
  status:
    | 'ok'
    | 'previous_crop_unknown'
    | 'no_harvest_in_calendar'
    | 'no_weather_record'
    | 'weather_record_too_short';
  afterCrop: string | null;
  harvestDoy: number | null;
  seedingDoy: number | null;
  calendarKind: string | null;
  seasonsTotal: number;
  firstKillingFrostDoy: number | null;
  options: RotationOffSeasonOption[];
};

export type RotationAdviceRequest = {
  fieldId: string;
  crop?: string;
  priorities: RotationPriority[];
};
