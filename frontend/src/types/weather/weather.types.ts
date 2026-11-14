export interface WeatherRecord {
  key: number;
  date: string;
  today: boolean;
  conditions: string;
  weatherCode: number | null;
  temperature: number | null;
  low: number | null;
  rainfall: number | null;
  humidity: number | null;
  wind: number | null;
  windDirection: number | null;
  moisture: number | null;
  rainChance: number | null;
  cropAssessment: CropDayAssessment | null;
}

export type WeatherMetric = 'temperature' | 'rainfall' | 'moisture' | 'humidity' | 'wind';

export interface WeatherUnits {
  temperature: string;
  rainfall: string;
  wind: string;
  humidity: string;
  moisture: string;
}

export interface WeatherMetadata {
  location: string;
  latitude: number;
  longitude: number;
  gridLatitude: number;
  gridLongitude: number;
  timeZone: string;
  fetchedAt: string;
  source: string;
  sourceUrl: string;
  units: WeatherUnits;
  soilDepth: string;
  dataKind: 'forecast' | 'historical_model';
}

export interface WeatherSeries extends WeatherMetadata {
  cropAssessment: CropAssessment | null;
  records: WeatherRecord[];
}

export type WeatherCondition = 'sunny' | 'cloudy' | 'rain' | 'snow' | 'fog';

export interface CurrentWeather extends WeatherMetadata {
  observedAt: string;
  condition: WeatherCondition;
  temperature: number | null;
  conditions: string;
  feelsLike: number | null;
  high: number | null;
  low: number | null;
  humidity: number | null;
  wind: number | null;
  windDirection: number | null;
  rainChance: number | null;
  forecast: WeatherRecord[];
}

export type CropRiskLevel = 'good' | 'caution' | 'high' | 'unknown';

export interface CropMetricBounds {
  unit: string;
  criticalLow: number | null;
  goodLow: number;
  ideal: number;
  goodHigh: number;
  criticalHigh: number | null;
}

export interface CropRiskAlert {
  metric: WeatherMetric;
  reading: 'value' | 'low';
  severity: 'caution' | 'high';
  code: 'below_critical' | 'below_good' | 'above_good' | 'above_critical';
  value: number;
  boundary: number;
  unit: string;
  ruleId?: string;
  drivers?: { ruleId: string; input: string; value: number | string; unit: string | null }[];
}

export interface CropMetricAssessment {
  riskLevel: CropRiskLevel;
  valueRiskLevel: CropRiskLevel;
  lowRiskLevel: CropRiskLevel | null;
  suitabilityScore: number | null;
}

export interface CropDayAssessment {
  bounds: Record<WeatherMetric, CropMetricBounds>;
  suitabilityScore: number | null;
  riskLevel: CropRiskLevel;
  coverage: 'complete' | 'partial' | 'unavailable';
  metrics: Record<WeatherMetric, CropMetricAssessment>;
  alerts: CropRiskAlert[];
}

export interface CropAssessment {
  model: {
    id: string;
    version: string;
    kind: 'heuristic_stub' | 'rule_engine' | 'ml_model';
    scoreMeaning: 'suitability_0_bad_100_good';
  };
  context: {
    fieldId: string;
    fieldName: string;
    crop: string;
    latitude: number;
    longitude: number;
    soil: {
      soilType: string | null;
      soilPh: number | null;
      organicMatter: number | null;
      waterCapacity: number | null;
      drainage: string | null;
    };
    soilCoverage?: 'complete' | 'partial' | 'unavailable';
    climate: {
      source: 'forecast_window' | 'history_window';
      startDate: string;
      endDate: string;
      meanHigh: number | null;
      meanLow: number | null;
      meanHumidity: number | null;
      meanDailyRainfall: number | null;
      sampleDays: number;
    };
  };
  bounds: Record<WeatherMetric, CropMetricBounds>;
}
