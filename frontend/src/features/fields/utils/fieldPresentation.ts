import { CheckCircle2, CircleAlert, TriangleAlert } from 'lucide-react';

export const fieldStatusPresentation = {
  Healthy: { icon: CheckCircle2, color: 'success', stroke: '#7a9b63' },
  Critical: { icon: TriangleAlert, color: 'error', stroke: '#b75f4e' },
  'Needs attention': { icon: CircleAlert, color: 'warning', stroke: '#b8954d' },
};
export function getNitrogenAssessment(nitrogen: number) {
  if (nitrogen < 20) {
    return { color: 'error', label: 'Very low' };
  }
  if (nitrogen < 30) {
    return { color: 'warning', label: 'Low' };
  }
  return { color: 'success', label: 'Adequate' };
}
