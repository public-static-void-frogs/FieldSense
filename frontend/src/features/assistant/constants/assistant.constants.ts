// Mirrors the backend limits in app/schemas/assistant.py.
export const MAX_HISTORY_MESSAGES = 20;
export const MAX_MESSAGE_CHARS = 4000;

export const assistantSuggestions = [
  'Is there a frost risk this week?',
  'When is the best time to plant?',
  'How depleted is this soil?',
] as const;

// English phrases are translation keys; they are translated where they are rendered.
export const toolProgressLabels: Record<string, string> = {
  get_weather_forecast: 'Checking the forecast…',
  get_m3_insights: 'Looking up climate timing and risk…',
  get_neighbour_evidence: 'Checking evidence from neighbouring fields…',
  get_rotation_advice: 'Reviewing crop recommendations…',
  get_calendar_events: 'Reading calendar events…',
  get_crop_production: 'Looking up crop production…',
  get_crop_revenue: 'Estimating crop revenue…',
  get_soil_moisture: 'Checking soil moisture…',
  get_soil_depletion: 'Checking soil depletion…',
};

export type AssistantErrorKind = 'unavailable' | 'interrupted' | 'failed';

export const assistantErrorMessages: Record<AssistantErrorKind, string> = {
  unavailable: 'The assistant is unavailable right now. Try again in a moment.',
  interrupted: 'The answer was interrupted.',
  failed: 'Something went wrong. Please try again.',
};
