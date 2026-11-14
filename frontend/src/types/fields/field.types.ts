import type { MultiPolygon, Point } from 'geojson';
import type { FieldPropertyData } from './api.types.ts';

export type FieldStatus = 'Healthy' | 'Needs attention' | 'Critical';

export interface Field {
  id: string;
  parcelId: number | null;
  geometry: Point;
  boundary?: MultiPolygon | null;
  properties: FieldPropertyData | null;
  name: string;
  crop: string | null;
  area: number;
  health: number | null;
  moisture: number | null;
  nitrogen: number | null;
  status: FieldStatus | null;
  planted: string | null;
  sourceId: string | null;
  locationKind: 'user_point' | 'interior_point' | 'crop_area';
  sourceYear: number | null;
  county: string | null;
  stateFips: string | null;
  countyFips: string | null;
}
