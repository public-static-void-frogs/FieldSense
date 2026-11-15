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
      /** 'loss': level from expectedLoss; 'frequency': no measured loss, level from share. */
      levelBasis?: 'loss' | 'frequency';
      /** Share of yield lost in a season the hazard hits, measured in county yields. */
      lossWhenHit?: {
        loss: number;
        se: number;
        sample: 'all' | 'dryland';
        finding: 'loss' | 'no_loss_found';
        countyYears: number;
      } | null;
      /** Share of seasons hit x lossWhenHit.loss. */
      expectedLoss?: number | null;
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
  threshold?: number | null;
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
  /** Rank by rotation risk alone; `rank` follows the plan when one could be priced. */
  riskRank?: number;
  tier?: 'top' | 'alternative' | 'not_modelled';
  notModelledCode?: string | null;
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
    /** Seasons taken from the farmer's own results instead of the satellite label. */
    declaredSeasons?: number;
    firstYear: number | null;
    lastYear: number | null;
    satelliteEstimate: boolean;
  };
  history: RotationHistoryYear[];
  seasonsAvailable: number[];
  summarySource?: {
    kind: 'own' | 'weather_cell' | 'nearby_cell' | 'none';
    distanceKm: number | null;
  } | null;
  weatherRecord: RotationWeatherRecord | null;
  offSeason: RotationOffSeason | null;
  dataGaps: RotationDataGap[];
  candidates: RotationCandidate[];
  seasonTiming: RotationSeasonTiming | null;
  soilInputs?: RotationSoilInput[];
  plan?: RotationPlan | null;
};

export type RotationSoilInput = {
  id: 'ph' | 'organicMatterPct' | 'phosphorusPpm' | 'potassiumPpm';
  value: number;
  source: 'survey' | 'ssurgo';
  /** Empty: the value is stored but not yet part of the calculation. */
  usedIn: ('rules' | 'soil_carbon')[];
};

export type RotationEstablishment = 'reliable' | 'marginal' | 'unlikely';

export type RotationAutumnAction = 'none' | 'sow_cover_crop' | 'sow_winter_crop' | 'keep_stand';

/** One season of a plan. Money is USD per acre; net is revenue less production cost. */
export type RotationPlanStep = {
  season: number;
  crop: string;
  tillage: 'conventional' | 'strip_till' | 'no_till';
  coverCrop: 'none' | 'rye';
  autumnBefore: RotationAutumnAction;
  objectiveUsdPerAcre: number;
  netUsdPerAcre: number;
  worstYearUsdPerAcre: number;
  bestYearUsdPerAcre: number;
  worstYear: number;
  revenueUsdPerAcre: number;
  costUsdPerAcre: number;
  /** The part of the cost spent on the crop in the season; null when the split is not known. */
  operatingCostUsdPerAcre?: number | null;
  riskPenaltyUsdPerAcre: number;
  soilValueUsdPerAcre: number;
  yieldPerAcre: number;
  yieldUnit: string;
  rules: string[];
};

export type RotationSimulatedYear = { year: number; netUsdPerAcre: number };

export type RotationSimulatedSpread = {
  /** Share of results below the full cost (with labour, machinery ownership and overhead). */
  lossProbability: number;
  /** Share of results below the operating costs alone; null when the split is not known. */
  operatingLossProbability?: number | null;
  meanUsdPerAcre: number;
  p10UsdPerAcre: number;
  p50UsdPerAcre: number;
  p90UsdPerAcre: number;
  worst: RotationSimulatedYear;
  best: RotationSimulatedYear;
};

/** The first season if this past year's weather and price came again. */
export type RotationSimulatedOutcome = {
  year: number;
  probability: number;
  netUsdPerAcre: number;
  yieldPerAcre: number;
  priceUsd: number;
  yieldMode: 'observed' | 'modelled' | 'none';
};

export type RotationPlanSimulation = {
  firstSeason: RotationSimulatedSpread & {
    years: number;
    yieldPerAcre: {
      unit: string;
      meanPerAcre: number;
      p10PerAcre: number;
      p50PerAcre: number;
      p90PerAcre: number;
    };
    planningPriceUsd: number;
    observedYieldYears: number;
    beatsTopProbability: number | null;
    outcomes: RotationSimulatedOutcome[];
  };
  plan: (RotationSimulatedSpread & { runs: number }) | null;
};

/** The best plan that starts with this crop. */
export type RotationPlanCrop = {
  crop: string;
  rank: number;
  tier: 'top' | 'alternative';
  demoted: 'autumn_establishment_unlikely' | null;
  planObjectiveUsdPerAcre: number;
  /** Learned plans only: how far the plan is below the exact best plan starting with this crop. */
  belowOptimumUsdPerAcre?: number | null;
  planNetUsdPerAcre: number;
  autumn: {
    action: RotationAutumnAction;
    species: string | null;
    establishment: RotationEstablishment | null;
    ryeCoverGainUsdPerAcre: number | null;
    ryeCoverEstablishment: RotationEstablishment | null;
  };
  steps: RotationPlanStep[];
  simulation: RotationPlanSimulation;
};

export type RotationOwnYieldLevel = {
  crop: string;
  yieldUnit: string;
  /** Field level over the county level; fewer than four years are filled at 1.0. */
  ratio: number;
  expectedYieldPerAcre: number;
  points: { year: number; yieldPerAcre: number; referenceYieldPerAcre: number }[];
};

/** How a plan is built: every rotation compared, or a trained policy choosing each season. */
export type RotationPlanner = 'exact' | 'learned';

export type RotationPlan = {
  status: 'ok' | 'no_modellable_crop';
  method?: 'dynamic_programming_fixed_sequence' | 'learned_policy' | null;
  planner?: {
    requested: RotationPlanner;
    used: RotationPlanner;
    learnedAvailable: boolean;
    learnedUnavailable: string | null;
  } | null;
  seasons: number;
  firstSeason: number | null;
  years: {
    source: 'climate_record' | 'field_seasons' | 'price_years';
    count: number;
    first: number;
    last: number;
  } | null;
  costRegion: string | null;
  yearOdds: {
    method: 'analog_years' | 'equal';
    effectiveYears: number;
    startsAfter: number | null;
    signals: string[];
  } | null;
  ownYields: RotationOwnYieldLevel[];
  crops: RotationPlanCrop[];
  notModelled: ({ crop: string; code: string } & Record<string, unknown>)[];
  gaps: RotationDataGap[];
  economics?: {
    landRentUsdPerAcre: number;
    landRentSource: 'farmer' | 'not_charged';
    crops: {
      crop: string;
      priceUsd: number;
      priceSource: 'farmer' | 'planning';
      costUsdPerAcre: number;
      costSource: 'farmer' | 'tables';
      soilTestCostChangeUsdPerAcre: number;
    }[];
  } | null;
  soilTest?: RotationSoilTestEffect[];
  soilYield?: {
    crop: string;
    index: 'nccpi_corn' | 'nccpi_soy';
    fieldIndex: number;
    countyIndex: number;
    countyFields: number;
    ratio: number;
    expectedYieldPerAcre: number;
    verified: boolean;
  }[];
};

/** What the farmer grew in one past season. Yield is bu/acre; hay is ton/acre. */
export type RotationSeasonResult = { year: number; crop: string; yieldPerAcre?: number | null };

export type RotationSeasonResults = { results: RotationSeasonResult[] };

/** The farmer's own soil test. pH and organic matter replace the soil survey estimate. */
export type RotationSoilSurvey = {
  sampledOn?: string | null;
  ph?: number | null;
  organicMatterPct?: number | null;
  phosphorusPpm?: number | null;
  potassiumPpm?: number | null;
  phosphorusTest?: 'bray_p1' | 'mehlich3_colorimetric' | 'mehlich3_icp' | 'olsen' | null;
  potassiumSample?: 'dried' | 'moist' | null;
};

/** The farmer's own price, cost and rent. What is left out keeps the USDA average. */
export type RotationEconomicsInputs = {
  landRentUsdPerAcre?: number | null;
  crops: { crop: string; priceUsd?: number | null; costUsdPerAcre?: number | null }[];
};

export type RotationLandRentDefault = {
  usdPerAcre: number;
  year: number;
  level: 'county' | 'state' | 'ers_region';
  source: 'nass_cash_rents' | 'ers_land_opportunity_cost';
};

export type RotationEconomics = {
  inputs: RotationEconomicsInputs | null;
  defaults: {
    costRegion: string | null;
    landRent: RotationLandRentDefault | null;
    irrigatedLandRent: RotationLandRentDefault | null;
    crops: {
      crop: string;
      priceUsd: number;
      priceUnit: string;
      priceLevel: string;
      costUsdPerAcre: number;
      costLevel: 'ers_region' | 'national' | 'state_budget';
      costYear: number | null;
      costItems: Record<string, number> | null;
    }[];
  };
};

export type RotationSoilTestCategory = 'very_low' | 'low' | 'optimum' | 'high' | 'very_high';

/** A soil-test nutrient: its category and what the recommended rate does to the cost. */
export type RotationSoilTestEffect = {
  nutrient: 'phosphorus' | 'potassium';
  ppm: number;
  test: string;
  category: RotationSoilTestCategory;
  yieldResponseProbability: number;
  fertilizerUnit: string;
  fertilizerUsdPerLb: number;
  calibration: 'iowa' | 'iowa_applied_elsewhere';
  verified: boolean;
  crops: {
    crop: string;
    rateLbPerAcre: number;
    maintenanceRateLbPerAcre: number;
    costChangeUsdPerAcre: number;
  }[];
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
  seasons?: number;
  planner?: RotationPlanner;
};
