import type { RotationAdvice, RotationAdviceRequest } from '../../types/rotation/rotation.types.ts';
import { request } from '../core/http.ts';

export function rotationAdvicePath({ fieldId, crop, priorities }: RotationAdviceRequest) {
  const query = new URLSearchParams();
  if (crop) {
    query.set('crop', crop);
  }
  for (const priority of priorities) {
    query.append('priorities', priority);
  }
  const suffix = query.size ? `?${query}` : '';

  return `/fields/${fieldId}/rotation-advice${suffix}`;
}

export const rotationApi = {
  // The first request for a field may also look up its soil, so it gets a longer timeout.
  getAdvice: (input: RotationAdviceRequest, signal?: AbortSignal): Promise<RotationAdvice | null> =>
    request(rotationAdvicePath(input), { signal, allowMissing: true, timeoutMs: 30_000 }),
};
