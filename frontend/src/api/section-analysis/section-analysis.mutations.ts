import { mutationOptions } from '@tanstack/react-query';
import {
  sectionAnalysisApi,
  type AnalysisProgress,
  type AnalyzeSectionInput,
} from './section-analysis.api.ts';

export const sectionAnalysisMutations = {
  analyze: () =>
    mutationOptions({
      mutationKey: ['section-analysis', 'analyze'],
      mutationFn: ({
        input,
        signal,
        onProgress,
      }: {
        input: AnalyzeSectionInput;
        signal: AbortSignal;
        onProgress: (progress: AnalysisProgress) => void;
      }) => sectionAnalysisApi.analyze(input, signal, onProgress),
      retry: false,
      gcTime: 0,
    }),
};
