import type { CurrentWeather, WeatherSeries } from '../../types/weather/weather.types.ts';
import { request } from '../core/http.ts';

export type HistoryRange = '7 days' | '30 days' | '90 days';
export type HistoryPeriod = { range: HistoryRange } | { startDate: string; endDate: string };

async function readInsight(response: Response, onDelta: (delta: string) => void) {
  const reader = response.body?.pipeThrough(new TextDecoderStream()).getReader();
  if (!reader) {
    throw new Error('Weather insight stream is unavailable');
  }

  let pending = '';
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        throw new Error('Weather insight stream ended before completion');
      }
      pending += value;
      const lines = pending.split('\n');
      pending = lines.pop() ?? '';
      for (const line of lines) {
        const event: { delta?: string; done?: boolean } = JSON.parse(line);
        if (event.done) {
          return;
        }
        if (typeof event.delta === 'string') {
          onDelta(event.delta);
        }
      }
    }
  } finally {
    void reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

export const weatherApi = {
  getCurrent: (signal?: AbortSignal): Promise<CurrentWeather> =>
    request('/weather/current', { signal }),
  getForecast: (signal?: AbortSignal, fieldId?: string): Promise<WeatherSeries> => {
    const params = new URLSearchParams();
    if (fieldId) {
      params.set('field_id', fieldId);
    }
    return request(`/weather/forecast?${params}`, { signal });
  },
  streamInsight: (
    day: string,
    locale: string,
    fieldId: string | undefined,
    signal: AbortSignal,
    onDelta: (delta: string) => void,
  ) => {
    const params = new URLSearchParams({ day, locale });
    if (fieldId) {
      params.set('field_id', fieldId);
    }
    return request(
      `/weather/forecast/insight?${params}`,
      { method: 'POST', signal, timeoutMs: 30_000 },
      (response) => readInsight(response, onDelta),
    );
  },
  getHistory: (
    period: HistoryPeriod,
    signal?: AbortSignal,
    fieldId?: string,
  ): Promise<WeatherSeries> => {
    const params = new URLSearchParams();
    if (fieldId) {
      params.set('field_id', fieldId);
    }
    if ('range' in period) {
      params.set('days', String(Number.parseInt(period.range)));
    } else {
      params.set('start_date', period.startDate);
      params.set('end_date', period.endDate);
    }
    return request(`/weather/history?${params}`, { signal });
  },
};
