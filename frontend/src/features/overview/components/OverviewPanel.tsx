import { Tooltip } from 'antd';
import { ArrowUpRight, CircleHelp } from 'lucide-react';
import { useId, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

type OverviewPanelProps = {
  title: string;
  icon: ReactNode;
  to: string;
  action: string;
  children: ReactNode;
  help?: ReactNode;
  className?: string;
};

export function OverviewPanel({
  title,
  icon,
  to,
  action,
  children,
  help,
  className = '',
}: OverviewPanelProps) {
  const id = useId();
  const { t } = useTranslation();

  return (
    <section className={`farm-panel ${className}`} aria-labelledby={id}>
      <header className="farm-panel-header">
        <div className="farm-panel-title">
          <h2 id={id}>
            {icon}
            {title}
          </h2>
          {help && (
            <Tooltip title={help} trigger={['hover', 'focus', 'click']}>
              <button
                className="farm-panel-help"
                type="button"
                aria-label={t('About {{label}}', { label: title })}
              >
                <CircleHelp size={16} aria-hidden />
              </button>
            </Tooltip>
          )}
        </div>
        <Link to={to}>
          {action}
          <ArrowUpRight size={15} aria-hidden />
        </Link>
      </header>
      {children}
    </section>
  );
}
