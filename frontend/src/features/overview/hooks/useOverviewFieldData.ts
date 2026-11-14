import { useQueries } from '@tanstack/react-query';
import { cropHistoryApi } from '../../../api/fields/crop-history.api.ts';
import { soilMoistureApi } from '../../../api/fields/soil-moisture.api.ts';
import { cropHistoryQueries } from '../../../api/fields/crop-history.queries.ts';
import { fieldInsightsQueries } from '../../../api/fields/field-insights.queries.ts';
import { soilMoistureQueries } from '../../../api/fields/soil-moisture.queries.ts';
import type { Field } from '../../../types/fields/field.types.ts';

// Keep live provider traffic bounded even when the farm has many saved fields.
let active = 0;
const waiting: (() => void)[] = [];

async function load<T>(signal: AbortSignal, request: () => Promise<T>): Promise<T> {
  if (active >= 4) {
    await new Promise<void>((resolve) => waiting.push(resolve));
  } else {
    active++;
  }
  try {
    signal.throwIfAborted();
    return await request();
  } finally {
    const next = waiting.shift();
    if (next) {
      next();
    } else {
      active--;
    }
  }
}

export function useOverviewFieldData(fields: Field[]) {
  const points = fields.map((field) => ({
    fieldId: field.id,
    part: 0,
    geometryKey: JSON.stringify(field.boundary?.coordinates[0] ?? field.geometry.coordinates),
  }));
  const cropHistory = useQueries({
    queries: points.map(({ fieldId, geometryKey }) => ({
      ...cropHistoryQueries.point(fieldId, 0, geometryKey, null),
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        load(signal, () => cropHistoryApi.point(fieldId, 0, null, signal)),
      placeholderData: undefined,
    })),
  });
  const climate = useQueries({
    queries: fields.map((field) =>
      fieldInsightsQueries.m3(field.id, JSON.stringify(field.geometry.coordinates)),
    ),
  });
  const moisture = useQueries({
    queries: points.map((point) => ({
      ...soilMoistureQueries.current(point),
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        load(signal, () => soilMoistureApi.current(point.fieldId, point.part, signal)),
    })),
  });
  const depletion = useQueries({
    queries: points.map(({ fieldId, geometryKey }) => ({
      ...fieldInsightsQueries.soil(fieldId, 0, geometryKey),
      enabled: false,
      refetchInterval: false as const,
    })),
  });

  return fields.map((field, index) => ({
    field,
    cropHistory: cropHistory[index],
    climate: climate[index],
    moisture: moisture[index],
    depletion: depletion[index].data?.assessment,
  }));
}
