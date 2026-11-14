import { useState } from 'react';
import type { Dayjs } from 'dayjs';
import type { HistoryPeriod, HistoryRange } from '../../../api/weather/weather.api.ts';

export function useWeatherSelection() {
  const [range, setRange] = useState<HistoryRange>('7 days');
  const [dates, setDates] = useState<[Dayjs, Dayjs] | null>(null);
  const [selectedKey, selectReading] = useState(0);

  function changeRange(value: HistoryRange) {
    setRange(value);
    setDates(null);
    selectReading(0);
  }

  function changeDates(values: [Dayjs | null, Dayjs | null] | null) {
    if (values?.[0] && values[1]) {
      setDates([values[0], values[1]]);
    } else {
      setDates(null);
    }
    selectReading(0);
  }

  let period: HistoryPeriod = { range };
  if (dates) {
    period = { startDate: dates[0].format('YYYY-MM-DD'), endDate: dates[1].format('YYYY-MM-DD') };
  }

  return { range, dates, period, changeRange, changeDates, selectedKey, selectReading };
}
