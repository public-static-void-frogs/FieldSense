import type {
  RotationAdvice,
  RotationAdviceRequest,
  RotationEconomics,
  RotationEconomicsInputs,
  RotationSeasonResult,
  RotationSeasonResults,
  RotationSoilSurvey,
} from '../../types/rotation/rotation.types.ts';
import { request } from '../core/http.ts';

export function rotationAdvicePath({
  fieldId,
  crop,
  priorities,
  seasons,
  planner,
}: RotationAdviceRequest) {
  const query = new URLSearchParams();
  if (crop) {
    query.set('crop', crop);
  }
  for (const priority of priorities) {
    query.append('priorities', priority);
  }
  if (seasons) {
    query.set('seasons', String(seasons));
  }
  if (planner === 'learned') {
    query.set('planner', planner);
  }
  const suffix = query.size ? `?${query}` : '';

  return `/fields/${fieldId}/rotation-advice${suffix}`;
}

export const rotationApi = {
  // The first request for a field may also look up its soil, so it gets a longer timeout.
  getAdvice: (input: RotationAdviceRequest, signal?: AbortSignal): Promise<RotationAdvice | null> =>
    request(rotationAdvicePath(input), { signal, allowMissing: true, timeoutMs: 30_000 }),
  resetInputs: (fieldId: string): Promise<void> =>
    request(`/fields/${fieldId}/rotation-inputs`, { method: 'DELETE' }, async () => undefined),
  getSeasonResults: (fieldId: string, signal?: AbortSignal): Promise<RotationSeasonResults> =>
    request(`/fields/${fieldId}/season-results`, { signal }),
  saveSeasonResults: ({
    fieldId,
    results,
  }: {
    fieldId: string;
    results: RotationSeasonResult[];
  }): Promise<RotationSeasonResults> =>
    request(`/fields/${fieldId}/season-results`, {
      method: 'PUT',
      body: JSON.stringify({ results }),
    }),
  getSoilSurvey: (fieldId: string, signal?: AbortSignal): Promise<RotationSoilSurvey | null> =>
    request(`/fields/${fieldId}/soil-survey`, { signal }),
  saveSoilSurvey: ({
    fieldId,
    survey,
  }: {
    fieldId: string;
    survey: RotationSoilSurvey;
  }): Promise<RotationSoilSurvey> =>
    request(`/fields/${fieldId}/soil-survey`, { method: 'PUT', body: JSON.stringify(survey) }),
  removeSoilSurvey: (fieldId: string): Promise<void> =>
    request(`/fields/${fieldId}/soil-survey`, { method: 'DELETE' }, async () => undefined),
  getEconomics: (fieldId: string, signal?: AbortSignal): Promise<RotationEconomics> =>
    request(`/fields/${fieldId}/economics`, { signal }),
  saveEconomics: ({
    fieldId,
    inputs,
  }: {
    fieldId: string;
    inputs: RotationEconomicsInputs;
  }): Promise<RotationEconomicsInputs> =>
    request(`/fields/${fieldId}/economics`, { method: 'PUT', body: JSON.stringify(inputs) }),
  removeEconomics: (fieldId: string): Promise<void> =>
    request(`/fields/${fieldId}/economics`, { method: 'DELETE' }, async () => undefined),
};
