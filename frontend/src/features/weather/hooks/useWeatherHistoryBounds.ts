import dayjs from 'dayjs';
import { useEffect, useState } from 'react';

export function useWeatherHistoryBounds(timeZone: string) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, []);
  const localDay = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date(now));

  return { minDate: dayjs('1940-01-01'), maxDate: dayjs(localDay).subtract(1, 'day') };
}
