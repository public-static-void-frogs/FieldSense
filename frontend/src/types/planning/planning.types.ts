export type PlanCategory =
  | 'Crop rotation'
  | 'Soil check'
  | 'Nutrition'
  | 'Irrigation'
  | 'Crop inspection'
  | 'Harvest'
  | 'Field preparation';

export type PlanPriority = 'Routine' | 'Important' | 'High priority';

export interface RotationPlan {
  id: string;
  nextCropId: string;
  followingCropId: string;
  fieldId: string;
  currentCrop: string;
  nextCrop: string;
  followingCrop: string;
  confidence: number;
  sowingDate: string;
  windowEnd: string;
  followingDate: string;
  dateExplanation: string;
  reasons: string[];
  inputs: { label: string; value: string }[];
}
export interface PlannedEvent {
  id: string;
  fieldId: string;
  fieldName: string;
  date: string;
  category: PlanCategory;
  title: string;
  description: string;
  priority: PlanPriority;
  duration: string;
  rationale: string;
}

export type EventDecision = 'proposed' | 'accepted' | 'declined';
export interface EventResponse {
  status: Exclude<EventDecision, 'proposed'>;
  fingerprint: string;
}
export type EventResponses = Record<string, EventResponse>;
export interface StrategyForecast {
  date: string;
  stage: string;
  progress: number;
  health: number;
  currentHealth: number;
  healthImprovement: number[];
  range: number[];
}
export interface FieldStrategy {
  plan: RotationPlan;
  events: PlannedEvent[];
  steps: { event: PlannedEvent; checkpoint: string }[];
  forecast: StrategyForecast[];
  comparison: { name: string; current: number; projected: number }[];
  technicals: { key: string; parameter: string; value: string; role: string }[];
  contingencies: { condition: string; action: string }[];
}

export interface PlanningContext {
  today: string;
}
export type EventStatus = 'Completed' | 'Due soon' | 'Planned';
