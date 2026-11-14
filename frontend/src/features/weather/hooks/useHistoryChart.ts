import { useId } from 'react';
import { useTranslation } from 'react-i18next';
import { useChartAnimation } from '../../../hooks/useChartAnimation.ts';
import type {
  WeatherMetric,
  WeatherRecord,
  WeatherUnits,
} from '../../../types/weather/weather.types.ts';

import { getWeatherMetricConfig, selectWeatherReading } from '../utils/weatherPresentation.ts';

type UseHistoryChartOptions = {
  records: WeatherRecord[];
  metric: WeatherMetric;
  selectedKey: number;
  onSelect: (key: number) => void;
  units: WeatherUnits;
  forecast?: boolean;
};

type HistoryChartSelection = {
  activeTooltipIndex?: number | string | null;
};

export function useHistoryChart({
  records,
  metric,
  selectedKey,
  onSelect,
  units,
  forecast = false,
}: UseHistoryChartOptions) {
  const { t } = useTranslation();
  const gradientId = useId();
  const animate = useChartAnimation();
  const config = getWeatherMetricConfig(metric, t, units);
  const timeline = forecast ? records : [...records].reverse();
  const selected = selectWeatherReading(records, selectedKey);

  function selectPoint(state: HistoryChartSelection) {
    if (state.activeTooltipIndex == null) {
      return;
    }
    const record = timeline[Number(state.activeTooltipIndex)];
    if (record) {
      onSelect(record.key);
    }
  }
  return { gradientId, animate, config, timeline, selected, selectPoint };
}
