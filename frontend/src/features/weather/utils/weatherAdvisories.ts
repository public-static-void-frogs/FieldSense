import type { WeatherSeries } from '../../../types/weather/weather.types.ts';

export function weatherAdvisories(series: WeatherSeries) {
  const freezing = series.units.temperature === '°F' ? 32 : 0;
  const strongWind = series.units.wind === 'mph' ? 24.85 : 40;
  return series.records.slice(0, 3).flatMap((record) => {
    const messages: { date: string; message: string }[] = [];
    if (record.low !== null && record.low <= freezing) {
      messages.push({ date: record.date, message: 'Freezing temperatures are forecast.' });
    }
    if (record.wind !== null && record.wind >= strongWind) {
      messages.push({ date: record.date, message: 'Strong wind is forecast.' });
    }
    if (record.rainChance !== null && record.rainChance >= 60) {
      messages.push({ date: record.date, message: 'Precipitation is likely.' });
    }
    return messages;
  });
}
