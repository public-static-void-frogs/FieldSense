import { mutationOptions, type QueryClient } from '@tanstack/react-query';
import { rotationApi } from './rotation.api.ts';
import { rotationQueryKeys } from './rotation.queries.ts';

// The farmer's inputs change the advice, so saving one refetches everything for the field.
const refresh = (client: QueryClient, fieldId: string) =>
  client.invalidateQueries({ queryKey: rotationQueryKeys.field(fieldId) });

export const rotationMutations = {
  saveSeasonResults: (client: QueryClient, fieldId: string) =>
    mutationOptions({
      mutationKey: ['rotation', 'season-results', fieldId],
      mutationFn: rotationApi.saveSeasonResults,
      onSuccess: (saved) => {
        client.setQueryData(rotationQueryKeys.seasonResults(fieldId), saved);

        return refresh(client, fieldId);
      },
    }),
  saveSoilSurvey: (client: QueryClient, fieldId: string) =>
    mutationOptions({
      mutationKey: ['rotation', 'soil-survey', fieldId],
      mutationFn: rotationApi.saveSoilSurvey,
      onSuccess: (saved) => {
        client.setQueryData(rotationQueryKeys.soilSurvey(fieldId), saved);

        return refresh(client, fieldId);
      },
    }),
  removeSoilSurvey: (client: QueryClient, fieldId: string) =>
    mutationOptions({
      mutationKey: ['rotation', 'soil-survey', fieldId, 'remove'],
      mutationFn: rotationApi.removeSoilSurvey,
      onSuccess: () => {
        client.setQueryData(rotationQueryKeys.soilSurvey(fieldId), null);

        return refresh(client, fieldId);
      },
    }),
  saveEconomics: (client: QueryClient, fieldId: string) =>
    mutationOptions({
      mutationKey: ['rotation', 'economics', fieldId],
      mutationFn: rotationApi.saveEconomics,
      onSuccess: (saved) => {
        client.setQueryData(rotationQueryKeys.economics(fieldId), saved);

        return refresh(client, fieldId);
      },
    }),
  removeEconomics: (client: QueryClient, fieldId: string) =>
    mutationOptions({
      mutationKey: ['rotation', 'economics', fieldId, 'remove'],
      mutationFn: rotationApi.removeEconomics,
      onSuccess: () => refresh(client, fieldId),
    }),
};
