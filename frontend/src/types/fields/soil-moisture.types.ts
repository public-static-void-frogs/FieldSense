export type MoistureSource = 'openmeteo' | 'power';
export type MoistureFrequency = 'daily' | 'hourly';

export type MoisturePeriod = {
  start: string;
  end: string;
  source: MoistureSource;
  frequency: MoistureFrequency;
};

export type CurrentSoilMoisture = {
  coordinates: [number, number];
  grid_point: [number, number] | null;
  time_utc: string | null;
  layers: Record<string, number | null>;
  profile_mean: number | null;
  unit: 'm3/m3';
};

export type MoistureStats = {
  n: number;
  mean: number;
  min: number;
  max: number;
  p10: number;
  p50: number;
  p90: number;
};

export type SoilMoistureHistory = MoisturePeriod & {
  coordinates: [number, number];
  unit: 'm3/m3' | 'fraction_of_saturation';
  series: { date: string; time_utc: string | null; values: Record<string, number | null> }[];
  stats: Record<string, MoistureStats>;
};

export type SoilMoistureComparison = {
  current: CurrentSoilMoisture;
  window_days: number;
  years: Record<string, number>;
  unavailable_years: number[];
  past_mean: number | null;
  anomaly: number | null;
  percentile: number | null;
};
