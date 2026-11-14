import { useEffect, useRef } from 'react';
import type {
  CropMetricBounds,
  WeatherMetric,
  WeatherRecord,
} from '../../../types/weather/weather.types.ts';
import { cropBoundsAtPosition, cropZoneGradient } from '../utils/cropRiskPresentation.ts';

type UseWeatherRiskCanvasOptions = {
  records: WeatherRecord[];
  metric: WeatherMetric;
  fallback: CropMetricBounds;
  minimum: number;
  maximum: number;
  width: number;
  height: number;
  padding: number;
};

export function useWeatherRiskCanvas({
  records,
  metric,
  fallback,
  minimum,
  maximum,
  width,
  height,
  padding,
}: UseWeatherRiskCanvasOptions) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || width <= 0 || height <= 0) {
      return;
    }
    canvas.width = Math.ceil(width);
    canvas.height = Math.ceil(height);
    const context = canvas.getContext('2d');
    if (!context) {
      return;
    }
    // Only interpolate the model's limits for painting. Risk classification stays on the backend.
    for (let column = 0; column < canvas.width; column += 1) {
      const position =
        ((column - padding) / Math.max(1, width - padding * 2)) * Math.max(0, records.length - 1);
      const bounds = cropBoundsAtPosition(records, metric, fallback, position);
      if (!bounds) {
        continue;
      }
      const gradient = context.createLinearGradient(0, 0, 0, canvas.height);
      for (const stop of cropZoneGradient(bounds, minimum, maximum)) {
        gradient.addColorStop(stop.offset / 100, stop.color);
      }
      context.fillStyle = gradient;
      context.fillRect(column, 0, 1, canvas.height);
    }
  }, [records, metric, fallback, minimum, maximum, width, height, padding]);
  return ref;
}
