export type TrendMetric = 'health' | 'moisture';
export type FieldTrend = Record<string, string | number>;
export interface CropArea {
  name: string;
  area: number;
  fill: string;
}
export interface OverviewData {
  trends: FieldTrend[];
  cropAreas: CropArea[];
}
