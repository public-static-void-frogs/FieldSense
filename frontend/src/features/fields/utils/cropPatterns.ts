import { decode } from 'fast-png';
import type {
  CropHistoryLayer,
  CropHistoryPoint,
  CropHistoryYear,
  HistoricalCropClass,
} from '../../../types/fields/crop-history.types.ts';

type AnnualLayer = { year: number; layer: CropHistoryLayer };

type CropPatterns = {
  bounds: CropHistoryLayer['bounds'];
  width: number;
  height: number;
  colors: Uint8ClampedArray<ArrayBuffer>;
  classes: HistoricalCropClass[];
  hasMixed: boolean;
  crops: Map<number, HistoricalCropClass>;
  annual: { year: number; cells: Uint8Array | null }[];
};

export function buildCropPatterns(layers: AnnualLayer[]): CropPatterns | null {
  const crops = new Map<number, HistoricalCropClass>();
  let grid: { bounds: CropHistoryLayer['bounds']; width: number; height: number } | undefined;
  const annual = layers.map(({ year, layer }) => {
    if (!layer.image) {
      return { year, cells: null };
    }

    // Read unmodified RGB values. Canvas can round channels when decoding translucent pixels.
    const bytes = Uint8Array.from(atob(layer.image.split(',')[1]), (char) => char.charCodeAt(0));
    const { width, height, data, depth, channels } = decode(bytes);
    grid ??= { bounds: layer.bounds, width, height };
    if (
      depth !== 8 ||
      channels !== 4 ||
      width !== grid.width ||
      height !== grid.height ||
      layer.bounds.some((value, index) => value !== grid?.bounds[index])
    ) {
      throw new Error('Crop maps do not share an RGBA pixel grid');
    }

    const palette = new Map<number, number>();
    for (const crop of layer.classes) {
      const rgb = parseInt(crop.color.slice(1), 16);
      if (palette.has(rgb) && palette.get(rgb) !== crop.code) {
        throw new Error('Crop map contains multiple classes with the same color');
      }
      palette.set(rgb, crop.code);
      crops.set(crop.code, { code: crop.code, color: crop.color, label: crop.label });
    }
    const cells = new Uint8Array(width * height);
    for (let index = 0; index < cells.length; index++) {
      const offset = index * 4;
      if (data[offset + 3] === 0) {
        continue;
      }
      const rgb = (data[offset] << 16) | (data[offset + 1] << 8) | data[offset + 2];
      const code = palette.get(rgb);
      if (code === undefined) {
        throw new Error('Crop map contains a color absent from its legend');
      }
      cells[index] = code;
    }

    return { year, cells };
  });

  if (!grid) {
    return null;
  }

  const { width, height, bounds } = grid;
  const colors = new Uint8ClampedArray(width * height * 4);
  const palette = new Map(
    [...crops].map(([code, crop]) => [code, parseInt(crop.color.slice(1), 16)]),
  );
  const dominant = new Set<number>();
  const counts = new Uint8Array(256);
  let hasMixed = false;

  for (let index = 0; index < width * height; index++) {
    let total = 0;
    let leader = 0;
    let most = 0;
    for (const { cells } of annual) {
      const code = cells?.[index] ?? 0;
      if (code === 0) {
        continue;
      }
      total++;
      const count = ++counts[code];
      if (count > most) {
        leader = code;
        most = count;
      }
    }
    for (const { cells } of annual) {
      counts[cells?.[index] ?? 0] = 0;
    }
    if (total === 0) {
      continue;
    }

    const offset = index * 4;
    if (most * 2 > total) {
      const rgb = palette.get(leader) ?? 0;
      colors.set([rgb >> 16, (rgb >> 8) & 255, rgb & 255, 210], offset);
      dominant.add(leader);
    } else {
      const shade = ((index % width) + Math.floor(index / width)) % 6 < 3 ? 235 : 92;
      colors.set([shade, shade, shade, 225], offset);
      hasMixed = true;
    }
  }

  return {
    bounds,
    width,
    height,
    colors,
    classes: [...crops.values()].filter(({ code }) => dominant.has(code)),
    hasMixed,
    crops,
    annual,
  };
}

function mercatorLatitude(latitude: number) {
  return Math.asinh(Math.tan((latitude * Math.PI) / 180));
}

export function cropPatternAt(pattern: CropPatterns, point: CropHistoryPoint): CropHistoryYear[] {
  const [west, south, east, north] = pattern.bounds;
  const [longitude, latitude] = point;
  if (longitude < west || longitude > east || latitude < south || latitude > north) {
    return [];
  }

  const { width, height } = pattern;
  const x = Math.min(width - 1, Math.floor(((longitude - west) / (east - west)) * width));
  const top = mercatorLatitude(north);
  const fraction = (top - mercatorLatitude(latitude)) / (top - mercatorLatitude(south));
  const y = Math.min(height - 1, Math.floor(fraction * height));
  const index = y * width + x;

  return pattern.annual.map(({ year, cells }) => ({
    year,
    crop: pattern.crops.get(cells?.[index] ?? 0) ?? null,
  }));
}

export function summarizeCropPattern(years: CropHistoryYear[]) {
  const counts = new Map<HistoricalCropClass['code'], number>();
  let observed = 0;
  for (const { crop } of years) {
    if (crop) {
      observed++;
      counts.set(crop.code, (counts.get(crop.code) ?? 0) + 1);
    }
  }
  const dominant = years.find(
    ({ crop }) => crop && (counts.get(crop.code) ?? 0) * 2 > observed,
  )?.crop;

  return { observed, dominant, occurrences: dominant ? counts.get(dominant.code) : undefined };
}
