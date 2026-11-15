import { Info } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import './CustomMetricsBanner.css';

export function LearnedPlannerBanner() {
  const { t } = useTranslation();

  return (
    <div className="rotation-metrics-banner rotation-learned-banner">
      <div className="rotation-metrics-banner-message" role="status">
        <Info size={15} aria-hidden="true" />
        <span>{t('Experimental RL planner is applied')}</span>
      </div>
    </div>
  );
}
