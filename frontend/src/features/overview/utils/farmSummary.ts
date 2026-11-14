import type { Field } from '../../../types/fields/field.types.ts';

export function getFarmSummary(fields: Field[]) {
  return fields.reduce(
    (summary, field) => {
      summary.totalArea += field.area;
      if (field.status === 'Critical' || field.status === 'Needs attention') {
        summary.attentionCount++;
      }
      if (field.status === 'Critical') {
        summary.criticalCount++;
      }
      return summary;
    },
    { totalArea: 0, attentionCount: 0, criticalCount: 0 },
  );
}
