import { Tooltip } from 'antd';
import { CircleHelp } from 'lucide-react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

type InsightHelpLabelProps = { label: string; help?: ReactNode };

export function InsightHelpLabel({ label, help }: InsightHelpLabelProps) {
  const { t } = useTranslation();

  return (
    <span className="field-insights-help-label">
      <span>{label}</span>
      {help && (
        <Tooltip title={help} trigger={['hover', 'focus', 'click']}>
          <button
            type="button"
            className="field-insights-help-button"
            aria-label={t('About {{label}}', { label })}
          >
            <CircleHelp size={16} aria-hidden="true" />
          </button>
        </Tooltip>
      )}
    </span>
  );
}
