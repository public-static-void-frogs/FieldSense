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
