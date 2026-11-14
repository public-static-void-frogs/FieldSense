import type { FieldStrategyOption } from '../../../types/fields/api.types.ts';

export const sampleFieldStrategies: FieldStrategyOption[] = [
  {
    id: 'soil-cover',
    crop: 'Winter wheat',
    description:
      'Keep living roots in the soil through winter to protect the surface from erosion and leave the field available after an early summer harvest.',
  },
  {
    id: 'nitrogen-fixation',
    crop: 'Soybeans',
    description:
      'Rotate in a legume that can get much of its nitrogen from the air. Soybeans can also interrupt some pest and disease cycles when grown between cereal crops.',
  },
  {
    id: 'long-term-fertility',
    crop: 'Alfalfa',
    description:
      'Grow a perennial forage for several seasons. Its deep roots help build soil structure, and the stand keeps the soil covered between harvests.',
  },
];
