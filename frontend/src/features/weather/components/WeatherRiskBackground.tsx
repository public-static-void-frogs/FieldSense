import type {
  CropMetricBounds,
  WeatherMetric,
  WeatherRecord,
} from '../../../types/weather/weather.types.ts';
import { useWeatherRiskCanvas } from '../hooks/useWeatherRiskCanvas.ts';

type WeatherRiskBackgroundProps = {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  records: WeatherRecord[];
  metric: WeatherMetric;
  bounds: CropMetricBounds;
  minimum: number;
  maximum: number;
  padding: number;
};

export function WeatherRiskBackground({
  x = 0,
  y = 0,
  width = 0,
  height = 0,
  records,
  metric,
  bounds,
  minimum,
  maximum,
  padding,
}: WeatherRiskBackgroundProps) {
  const fullWidth = width + padding * 2;
  const ref = useWeatherRiskCanvas({
    records,
    metric,
    fallback: bounds,
    minimum,
    maximum,
    width: fullWidth,
    height,
    padding,
  });

  return (
    <foreignObject
      className="weather-risk-background"
      x={x - padding}
      y={y}
      width={fullWidth}
      height={height}
      pointerEvents="none"
    >
      <canvas
        ref={ref}
        style={{ width: '100%', height: '100%', display: 'block' }}
        aria-hidden="true"
      />
    </foreignObject>
  );
}
