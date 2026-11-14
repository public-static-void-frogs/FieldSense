export function recommendationPath(fieldId: string, cropId?: string) {
  const path = `/fields/${fieldId}/recommendation`;

  return cropId ? `${path}/${encodeURIComponent(cropId)}` : path;
}
