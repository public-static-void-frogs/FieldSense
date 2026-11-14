import { useSuspenseQueries } from '@tanstack/react-query';
import { MapPin, Plus, Sprout } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { fieldQueries } from '../api/fields/fields.queries.ts';
import { farmQueries } from '../api/farm/farm.queries.ts';
import { RouterButton } from '../components/common/RouterButton';
import { LegalLinks } from '../features/legal/components/LegalLinks.tsx';
import { OverviewInventory } from '../features/overview/components/OverviewInventory';
import { OverviewMonitoring } from '../features/overview/components/OverviewMonitoring';
import {
  OverviewAgenda,
  OverviewNotifications,
  OverviewWeather,
} from '../features/overview/components/OverviewOperations';
import '../features/legal/components/legal.css';
import '../features/overview/components/Overview.css';

export function OverviewPage() {
  const { t } = useTranslation();
  const [{ data: fields }, { data: profile }] = useSuspenseQueries({
    queries: [fieldQueries.list(), farmQueries.profile()],
  });

  return (
    <div className="farm-overview">
      <header className="farm-overview-heading">
        <div className="farm-overview-title">
          <h1>{t('Overview')}</h1>
          {profile.locationLabel && (
            <p>
              <MapPin size={15} aria-hidden />
              {profile.locationLabel}
            </p>
          )}
        </div>
        <RouterButton type="primary" icon={<Plus size={18} />} to="/map/add">
          {t('Add field')}
        </RouterButton>
      </header>
      <div className="farm-overview-grid">
        {fields.length > 0 ? (
          <OverviewInventory fields={fields} />
        ) : (
          <section className="farm-panel farm-panel-wide farm-empty">
            <Sprout size={32} aria-hidden />
            <h2>{t('Add your first field')}</h2>
            <p>{t('Choose your fields on the map to start tracking crop conditions.')}</p>
            <RouterButton to="/map/add">{t('Explore map')}</RouterButton>
          </section>
        )}
        <OverviewWeather profile={profile} />
        {fields.length > 0 && <OverviewMonitoring fields={fields} />}
        <OverviewAgenda />
        <OverviewNotifications />
      </div>
      <footer>
        <LegalLinks />
      </footer>
    </div>
  );
}
