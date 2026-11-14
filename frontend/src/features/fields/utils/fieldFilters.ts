import type { Field } from '../../../types/fields/field.types.ts';

import type { LandEvent } from '../../../types/fields/history.types.ts';

export type FieldFilters = {
  overview: boolean;
  query: string;
  status: string;
  crop: string;
  filters: string[];
};

export function filterFields(fields: Field[], options: FieldFilters) {
  const { overview, query, status, crop, filters } = options;
  const selectedCrops = filters.filter((key) => key.startsWith('crop:')).map((key) => key.slice(5));
  const search = query.trim().toLowerCase();
  return fields.filter((field) => {
    const searchable = overview
      ? field.name
      : `${field.name} ${field.crop} ${field.id} Field${String(field.parcelId).padStart(2, '0')}`;
    if (!searchable.toLowerCase().includes(search)) {
      return false;
    }
    if (
      status === 'Needs attention' &&
      field.status !== 'Critical' &&
      field.status !== 'Needs attention'
    ) {
      return false;
    }
    if (status !== 'All fields' && status !== 'Needs attention' && field.status !== status) {
      return false;
    }
    if (overview) {
      return crop === 'All crops' || field.crop === crop;
    }
    if (selectedCrops.length && !selectedCrops.includes(field.crop ?? '')) {
      return false;
    }
    if (filters.includes('moisture:low') && (field.moisture === null || field.moisture >= 40)) {
      return false;
    }
    if (filters.includes('health:low') && (field.health === null || field.health >= 70)) {
      return false;
    }
    if (filters.includes('area:large') && field.area < 25) {
      return false;
    }
    return true;
  });
}
export function filterLandHistory(
  events: LandEvent[],
  category: string,
  year: string,
  query: string,
) {
  return events.filter(
    (event) =>
      (category === 'All activities' || event.category === category) &&
      (year === 'All years' || event.date.startsWith(year)) &&
      `${event.title} ${event.description} ${event.measurements?.join(' ')}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
}
