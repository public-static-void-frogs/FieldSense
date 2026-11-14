import { useState } from 'react';
import type { CropArea } from '../../../types/overview/overview.types.ts';

export function useCropSelection(areas: CropArea[]) {
  const [crop, setCrop] = useState<string | null>(null);
  const activeCrop = areas.some((area) => area.name === crop) ? crop : null;
  function selectCrop(name: string) {
    setCrop((current) => (current === name ? null : name));
  }
  return { activeCrop, selectCrop };
}
