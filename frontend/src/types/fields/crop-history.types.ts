export type CropHistoryPoint = [longitude: number, latitude: number];

export interface HistoricalCropClass {
  code: number;
  label: string;
  color: string;
}

export interface CropHistoryYear {
  year: number;
  crop: HistoricalCropClass | null;
}

export interface CropHistory {
  coordinates: CropHistoryPoint;
  years: CropHistoryYear[];
}

export interface CropLayerClass extends HistoricalCropClass {
  share: number;
}

export interface CropHistoryLayer {
  bounds: [west: number, south: number, east: number, north: number];
  image: string | null;
  classes: CropLayerClass[];
}
