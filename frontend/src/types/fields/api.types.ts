import type { CropSeason, LandEvent } from './history.types.ts';
import type { FieldProperties } from './properties.types.ts';

export interface CropOption {
  value: string;
  label: string;
}
export interface FieldPropertyData {
  soil: FieldProperties;
  crop: FieldProperties;
  growthStage: string | null;
  lastSample: string | null;
  cultivationPractice: string | null;
  tenure: string | null;
}
export interface FieldHistory {
  events: LandEvent[];
  seasons: CropSeason[];
}
export interface FieldRecommendationData {
  title: string;
  description: string;
}
