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
export function calendarLoader({ params }: LoaderFunctionArgs) {
  if (params.date && !isPlanDate(params.date)) {
    throw new Response(null, { status: 404 });
  }
  return null;
}
