import { hashKey, keepPreviousData, queryOptions } from '@tanstack/react-query';
import type { UserSettings } from '../../types/auth/auth.types.ts';
import type { HistoryPeriod } from './weather.api.ts';
import { weatherApi } from './weather.api.ts';

export type WeatherLocation = Pick<
  UserSettings,
  'latitude' | 'longitude' | 'location' | 'timeZone' | 'units'
>;

function locationKey(location: WeatherLocation) {
  return {
    latitude: location.latitude,
    longitude: location.longitude,
    location: location.location,
    timeZone: location.timeZone,
    units: location.units,
  };
}

const cropAssessmentContractVersion = 'crop-rules-v1';

export const weatherQueryKeys = {
  all: () => ['weather'] as const,
  current: (location: WeatherLocation) => ['weather', locationKey(location), 'current'] as const,
  forecast: (location: WeatherLocation, fieldId?: string) =>
    [
      'weather',
      locationKey(location),
      'forecast',
      fieldId ?? null,
      cropAssessmentContractVersion,
    ] as const,
  history: (location: WeatherLocation, period: HistoryPeriod, fieldId?: string) =>
    [
      'weather',
      locationKey(location),
      'history',
      period,
      fieldId ?? null,
      cropAssessmentContractVersion,
    ] as const,
};

const pollingOptions = {
  staleTime: 5 * 60_000,
  refetchInterval: 10 * 60_000,
  retry: false,
};

export const weatherQueries = {
  current: (location: WeatherLocation) =>
    queryOptions({
      ...pollingOptions,
      queryKey: weatherQueryKeys.current(location),
      queryFn: ({ signal }) => weatherApi.getCurrent(signal),
      enabled: location.latitude !== null && location.longitude !== null,
    }),
  forecast: (location: WeatherLocation, fieldId?: string) =>
    queryOptions({
      ...pollingOptions,
      queryKey: weatherQueryKeys.forecast(location, fieldId),
      queryFn: ({ signal }) => weatherApi.getForecast(signal, fieldId),
      enabled: Boolean(fieldId) || (location.latitude !== null && location.longitude !== null),
    }),
  history: (location: WeatherLocation, period: HistoryPeriod, fieldId?: string) =>
    queryOptions({
      queryKey: weatherQueryKeys.history(location, period, fieldId),
      queryFn: ({ signal }) => weatherApi.getHistory(period, signal, fieldId),
      staleTime: 30 * 60_000,
      placeholderData: (previousData, previousQuery) => {
        if (!previousQuery) {
          return undefined;
        }
        const previousKey = previousQuery.queryKey;
        const sameLocation = hashKey([previousKey[1]]) === hashKey([locationKey(location)]);
        if (!sameLocation || previousKey[4] !== (fieldId ?? null)) {
          return undefined;
        }
        return keepPreviousData(previousData);
      },
      retry: false,
      enabled: Boolean(fieldId) || (location.latitude !== null && location.longitude !== null),
    }),
};
