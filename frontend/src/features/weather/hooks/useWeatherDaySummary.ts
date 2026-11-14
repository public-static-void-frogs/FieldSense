import { useEffect, useState } from 'react';
import { weatherApi } from '../../../api/weather/weather.api.ts';

export function useWeatherDaySummary(day: string, locale: string, fieldId?: string) {
  const [text, setText] = useState('');
  const [status, setStatus] = useState<'loading' | 'done' | 'failed'>('loading');

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void weatherApi
        .streamInsight(day, locale, fieldId, controller.signal, (delta) => {
          if (!controller.signal.aborted) {
            setText((previous) => previous + delta);
          }
        })
        .then(() => {
          if (!controller.signal.aborted) {
            setStatus('done');
          }
        })
        .catch(() => {
          if (!controller.signal.aborted) {
            setStatus('failed');
          }
        });
    }, 250);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [day, locale, fieldId]);

  return { text, loading: status === 'loading', failed: status === 'failed' };
}
