import type { PlanCategory } from '../../../types/planning/planning.types.ts';

export const planCategories: PlanCategory[] = [
  'Crop rotation',
  'Soil check',
  'Nutrition',
  'Irrigation',
  'Crop inspection',
  'Harvest',
  'Field preparation',
];

export const categoryColors: Record<PlanCategory, string> = {
  'Crop rotation': '#476b3c',
  'Soil check': '#805810',
  Nutrition: '#994835',
  Irrigation: '#245b83',
  'Crop inspection': '#62509a',
  Harvest: '#8b5b22',
  'Field preparation': '#536477',
};

export const categoryBackgrounds: Record<PlanCategory, string> = {
  'Crop rotation': '#e4efda',
  'Soil check': '#f9edcc',
  Nutrition: '#fae4dd',
  Irrigation: '#deedf9',
  'Crop inspection': '#ece5f7',
  Harvest: '#f4e8d3',
  'Field preparation': '#e6ecf2',
};
