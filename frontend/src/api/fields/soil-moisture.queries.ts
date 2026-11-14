import { queryOptions } from '@tanstack/react-query';
import type { MoisturePeriod } from '../../types/fields/soil-moisture.types.ts';
import { fieldQueryKeys } from './fields.queries.ts';
import { soilMoistureApi } from './soil-moisture.api.ts';

export type SoilMoistureLocation = { fieldId: string; part: number; geometryKey: string };

const tenMinutes = 10 * 60 * 1000;
const key = ({ fieldId, part, geometryKey }: SoilMoistureLocation) =>
  [...fieldQueryKeys.byId(fieldId), 'soil-moisture', part, geometryKey] as const;

export const soilMoistureQueries = {
  current: (location: SoilMoistureLocation) =>
    queryOptions({
      queryKey: key(location),
      queryFn: ({ signal }) => soilMoistureApi.current(location.fieldId, location.part, signal),
      staleTime: tenMinutes,
      retry: false,
    }),
  history: (location: SoilMoistureLocation, period: MoisturePeriod) =>
    queryOptions({
      queryKey: [...key(location), 'history', period],
      queryFn: ({ signal }) =>
        soilMoistureApi.history(location.fieldId, location.part, period, signal),
      staleTime: tenMinutes,
      retry: false,
    }),
  comparison: (location: SoilMoistureLocation) =>
    queryOptions({
      queryKey: [...key(location), 'comparison'],
      queryFn: ({ signal }) => soilMoistureApi.comparison(location.fieldId, location.part, signal),
      staleTime: tenMinutes,
      retry: false,
    }),
};
