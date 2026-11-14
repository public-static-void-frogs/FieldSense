import type { Polygon } from 'geojson';
import type { CropZone, DetectedField, MapBounds } from '../../types/maps/map.types.ts';
import { request } from '../core/http.ts';

export type AnalysisPoint = { id: string; coordinates: [number, number] };
export type SectionMapImage = {
  dataUrl: string;
  width: number;
  height: number;
  bounds: MapBounds;
  crs: 'EPSG:3857';
};
export type AnalyzeSectionInput = {
  points: AnalysisPoint[];
  image: SectionMapImage;
  region: Polygon;
};
export type SectionAnalysisResult = {
  requestId: string;
  mock: false;
  model: 'sam2-tiny+tempcnn';
  skippedPoints: { pointId: string; reason: string }[];
  provenance: {
    segmentationInputs: 'submitted_map_image_and_points';
    cropInputs: 'sentinel-2-l2a';
    syntheticCropInputs: false;
    sequenceShape: [16, 3];
    channels: ['NDVI', 'EVI', 'NDWI'];
    cropLabelSource: 'unmapped_class_indices' | 'training_class_mapping';
    classLabels: string[];
    device: string;
  };
  fields: DetectedField[];
  cropZones: CropZone[];
};

export type AnalysisProgress = {
  stage: 'segmentation' | 'satellite' | 'classification';
  completed: number;
  total: number;
};

type AnalysisEvent =
  | ({ type: 'progress' } & AnalysisProgress)
  | { type: 'result'; result: SectionAnalysisResult }
  | { type: 'error'; message: string }
  | { type: 'heartbeat' };

async function readAnalysis(
  response: Response,
  onProgress: (progress: AnalysisProgress) => void,
): Promise<SectionAnalysisResult> {
  if (!response.body) {
    throw new Error('Analysis response body is missing');
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = '';
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) {
        throw new Error('Analysis stream ended before the result');
      }
      const lines = (buffer + value).split('\n');
      buffer = lines.pop() ?? '';
      for (const line of lines) {
        const event = JSON.parse(line) as AnalysisEvent;
        if (event.type === 'progress') {
          onProgress(event);
        }
        if (event.type === 'error') {
          throw new Error(event.message);
        }
        if (event.type === 'result') {
          return event.result;
        }
      }
    }
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}

export const sectionAnalysisApi = {
  analyze: (
    input: AnalyzeSectionInput,
    signal: AbortSignal,
    onProgress: (progress: AnalysisProgress) => void,
  ): Promise<SectionAnalysisResult> =>
    request(
      '/maps/sections/analyze',
      {
        method: 'POST',
        headers: { Accept: 'application/x-ndjson' },
        body: JSON.stringify(input),
        signal,
        timeoutMs: 300_000,
      },
      (response) => readAnalysis(response, onProgress),
    ),
};
