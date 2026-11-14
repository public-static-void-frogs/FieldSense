import type { LoaderFunctionArgs } from 'react-router-dom';
import { isGuid } from '../utils/ids.ts';
import { isPlanDate } from '../features/planning/utils/planningDates.ts';

export type FieldRouteData = {
  fieldId: string;
};

export function fieldLoader({ params }: LoaderFunctionArgs): FieldRouteData {
  if (!isGuid(params.fieldId)) {
    throw new Response(null, { status: 404 });
  }
  return { fieldId: params.fieldId.toLowerCase() };
}
export type RecommendationCropRouteData = FieldRouteData & { cropId: string };

export function recommendationCropLoader(args: LoaderFunctionArgs): RecommendationCropRouteData {
  const { cropId } = args.params;
  if (!cropId) {
    throw new Response(null, { status: 404 });
  }

  return { ...fieldLoader(args), cropId };
}

export type StrategyOptionRouteData = FieldRouteData & { strategyId: string };

export function strategyOptionLoader(args: LoaderFunctionArgs): StrategyOptionRouteData {
  const { strategyId } = args.params;
  if (!strategyId) {
    throw new Response(null, { status: 404 });
  }
  return { ...fieldLoader(args), strategyId };
}
export function calendarLoader({ params }: LoaderFunctionArgs) {
  if (params.date && !isPlanDate(params.date)) {
    throw new Response(null, { status: 404 });
  }
  return null;
}
