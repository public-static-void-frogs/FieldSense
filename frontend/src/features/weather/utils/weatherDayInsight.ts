import type { WeatherRecord, WeatherUnits } from '../../../types/weather/weather.types.ts';

// Forecast-derived copy for the insight preview; no model-generated advice is implied.
export function getWeatherDayInsight(record: WeatherRecord, units: WeatherUnits) {
  const freezing = units.temperature === '°F' ? 32 : 0;
  const warm = units.temperature === '°F' ? 86 : 30;
  const strongWind = units.wind === 'mph' ? 40 / 1.609344 : 40;
  const wet = units.rainfall === 'in' ? 10 / 25.4 : 10;

  if (record.low !== null && record.low <= freezing) {
    return {
      title: 'A freezing night ahead.',
      message: 'The overnight low is the main change to watch, especially for early starts.',
    };
  }
  if (record.wind !== null && record.wind >= strongWind) {
    return {
      title: 'Wind stands out today.',
      message:
        'Wind is a prominent part of this forecast. Keep it in mind when planning outdoor work.',
    };
  }
  if (
    (record.rainChance !== null && record.rainChance >= 60) ||
    (record.rainfall !== null && record.rainfall >= wet)
  ) {
    return {
      title: 'Rain shapes the day ahead.',
      message: 'Allow some flexibility for outdoor work as rain may interrupt the day.',
    };
  }
  if (record.temperature !== null && record.temperature >= warm) {
    return {
      title: 'A warm day ahead.',
      message:
        'The daytime high is the standout reading. Compare it with the overnight low as you plan the day.',
    };
  }
  if (record.rainfall === 0 && record.rainChance !== null && record.rainChance < 20) {
    return {
      title: 'A mostly dry day ahead.',
      message:
        'Little rain is indicated in this forecast. Check the latest outlook before setting your plans.',
    };
  }
  if (
    [record.temperature, record.low, record.rainfall, record.rainChance, record.wind].every(
      (value) => value === null,
    )
  ) {
    return {
      title: 'More readings are needed.',
      message: 'There are not enough readings to summarize this day yet.',
    };
  }
  return {
    title: 'Your day’s weather outlook.',
    message: 'Use the daily readings together to plan around changing conditions.',
  };
}
