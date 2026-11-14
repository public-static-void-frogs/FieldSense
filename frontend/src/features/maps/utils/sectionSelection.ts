import type { CatalogFeature, CropZone } from '../../../types/maps/map.types.ts';
import { isPointInLasso } from './lassoSelection.ts';

export type SectionCoordinate = [latitude: number, longitude: number];
export type SectionField = { id: string; coordinates: [number, number] };
export type MapSection = {
  id: string;
  outline: SectionCoordinate[];
  fields: SectionField[];
  added: boolean;
  analysisStatus?: 'pending' | 'complete' | 'failed';
  analysisToken?: string;
  analysisError?: string;
  cropZones?: CropZone[];
  skippedCount?: number;
  excludedZones?: string[];
};
export type SectionSelection = {
  sections: MapSection[];
  looseFields: SectionField[];
  activeId: string | null;
};

export function toSectionField(feature: CatalogFeature): SectionField {
  return {
    id: String(feature.id),
    coordinates: [feature.geometry.coordinates[0], feature.geometry.coordinates[1]],
  };
}

export function selectedSectionIds(state: SectionSelection): Set<string> {
  return new Set(
    [...state.looseFields, ...state.sections.flatMap((section) => section.fields)].map(
      (field) => field.id,
    ),
  );
}

export function toggleSectionField(state: SectionSelection, field: SectionField): SectionSelection {
  if (selectedSectionIds(state).has(field.id)) {
    return {
      ...state,
      looseFields: state.looseFields.filter((item) => item.id !== field.id),
      sections: state.sections.map((section) => ({
        ...section,
        fields: section.fields.filter((item) => item.id !== field.id),
      })),
    };
  }
  let contained = false;
  const sections = state.sections.map((section) => {
    if (
      isPointInLasso(
        field.coordinates,
        section.outline.map(([latitude, longitude]) => [longitude, latitude]),
      )
    ) {
      contained = true;
      return { ...section, fields: [...section.fields, field] };
    }
    return section;
  });
  return {
    ...state,
    sections,
    looseFields: contained ? state.looseFields : [...state.looseFields, field],
  };
}

export function appendSection(state: SectionSelection, section: MapSection): SectionSelection {
  const ids = new Set(section.fields.map((field) => field.id));
  return {
    ...state,
    sections: [...state.sections, section],
    looseFields: state.looseFields.filter((field) => !ids.has(field.id)),
  };
}

export function cancelSection(state: SectionSelection, id: string): SectionSelection {
  return {
    ...state,
    sections: state.sections.filter((section) => section.id !== id),
    activeId: state.activeId === id ? null : state.activeId,
  };
}

/** Lightweight outline-area preview in hectares; backend analysis will replace this estimate. */
export function sectionArea(section: Pick<MapSection, 'outline'>): number {
  const origin = section.outline[0];
  if (!origin) {
    return 0;
  }
  const latitude = section.outline.reduce((sum, [lat]) => sum + lat, 0) / section.outline.length;
  const longitudeScale = 111_320 * Math.cos((latitude * Math.PI) / 180);
  let area = 0;
  for (let i = 0, j = section.outline.length - 1; i < section.outline.length; j = i++) {
    const [ay, ax] = section.outline[j];
    const [by, bx] = section.outline[i];
    area +=
      (ax - origin[1]) * longitudeScale * (by - origin[0]) * 111_320 -
      (bx - origin[1]) * longitudeScale * (ay - origin[0]) * 111_320;
  }
  return Math.abs(area) / 20_000;
}

/** Geographic centroid, falling back to the extent center for a self-crossing loop. */
export function sectionCenter(outline: SectionCoordinate[]): SectionCoordinate {
  const [oy, ox] = outline[0];
  let area = 0;
  let latitude = 0;
  let longitude = 0;
  for (let i = 0, j = outline.length - 1; i < outline.length; j = i++) {
    const ay = outline[j][0] - oy;
    const ax = outline[j][1] - ox;
    const by = outline[i][0] - oy;
    const bx = outline[i][1] - ox;
    const cross = ax * by - bx * ay;
    area += cross;
    latitude += (ay + by) * cross;
    longitude += (ax + bx) * cross;
  }
  if (Math.abs(area) > 1e-12) {
    return [oy + latitude / (3 * area), ox + longitude / (3 * area)];
  }
  return [
    (Math.min(...outline.map(([lat]) => lat)) + Math.max(...outline.map(([lat]) => lat))) / 2,
    (Math.min(...outline.map(([, lon]) => lon)) + Math.max(...outline.map(([, lon]) => lon))) / 2,
  ];
}

export function includedCropZones(section: MapSection): CropZone[] {
  const excluded = new Set(section.excludedZones ?? []);
  return (section.cropZones ?? []).filter((field) => !excluded.has(field.id));
}

export type DetectedCropGroup = {
  crop: CropZone['crop'];
  total: number;
  selected: number;
};

export function groupSectionCrops(section: MapSection): DetectedCropGroup[] {
  const excluded = new Set(section.excludedZones ?? []);
  const groups = new Map<CropZone['crop'], DetectedCropGroup>();
  for (const field of section.cropZones ?? []) {
    const group = groups.get(field.crop) ?? { crop: field.crop, total: 0, selected: 0 };
    group.total += 1;
    if (!excluded.has(field.id)) {
      group.selected += 1;
    }
    groups.set(field.crop, group);
  }
  return [...groups.values()].sort((first, second) => first.crop.localeCompare(second.crop));
}

export function setSectionCropSelection(
  section: MapSection,
  crop: CropZone['crop'],
  included: boolean,
): MapSection {
  const excluded = new Set(section.excludedZones ?? []);
  for (const field of section.cropZones ?? []) {
    if (field.crop !== crop) {
      continue;
    }
    if (included) {
      excluded.delete(field.id);
    } else {
      excluded.add(field.id);
    }
  }
  return { ...section, excludedZones: [...excluded] };
}
