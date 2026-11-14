import { useState } from 'react';
import type { TrendMetric } from '../../../types/overview/overview.types.ts';

export function useTrendControls() {
  const [days, setDays] = useState(30);
  const [metric, setMetric] = useState<TrendMetric>('health');
  const [hiddenFields, setHiddenFields] = useState<string[]>([]);
  function toggleField(id: string) {
    setHiddenFields((current) =>
      current.includes(id) ? current.filter((value) => value !== id) : [...current, id],
    );
  }
  return { days, setDays, metric, setMetric, hiddenFields, toggleField };
}
