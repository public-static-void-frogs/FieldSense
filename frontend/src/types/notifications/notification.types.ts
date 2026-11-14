export interface FarmNotification {
  id: string;
  kind: 'field' | 'weather';
  severity: 'warning' | 'error' | 'info';
  title: string;
  description: string;
  fieldId?: string;
  fieldName?: string;
}
