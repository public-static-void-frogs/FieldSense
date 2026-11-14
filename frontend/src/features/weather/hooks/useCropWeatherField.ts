import { useState } from 'react';
import type { CropOption } from '../../../types/fields/api.types.ts';
import type { Field } from '../../../types/fields/field.types.ts';

export function useCropWeatherField(fields: Field[], supportedCrops: CropOption[]) {
  const [selectedCrop, setSelectedCrop] = useState<string>();
  const [selectedFieldId, selectField] = useState<string>();
  const supported = new Map(supportedCrops.map((crop) => [crop.value.toLowerCase(), crop]));
  const cropFields = new Map<string, Field[]>();
  for (const field of fields) {
    const crop = supported.get(field.crop?.trim().toLowerCase() ?? '');
    if (crop) {
      const group = cropFields.get(crop.value) ?? [];
      group.push(field);
      cropFields.set(crop.value, group);
    }
  }
  const cropOptions = Array.from(cropFields.keys(), (value) => ({
    value,
    label: supported.get(value.toLowerCase())?.label ?? value,
  }));
  const crop = cropOptions.find((option) => option.value === selectedCrop) ?? cropOptions[0];
  const matchingFields = cropFields.get(crop?.value ?? '') ?? [];
  const field = matchingFields.find((item) => item.id === selectedFieldId) ?? matchingFields[0];

  function selectCrop(value: string) {
    setSelectedCrop(value);
    selectField(undefined);
  }

  return { crop, cropOptions, field, matchingFields, selectCrop, selectField };
}
