import { LegalLinks } from '../features/legal/components/LegalLinks.tsx';
import '../features/legal/components/legal.css';
import { useSuspenseQuery } from '@tanstack/react-query';
import { ArrowUpRight, CalendarDays, Plus } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { fieldQueries } from '../api/fields/fields.queries.ts';
import { PageHeading } from '../components/common/PageHeading';
import { RouterButton } from '../components/common/RouterButton';
import { CropFieldCards } from '../features/fields/components/CropFieldCards.tsx';
import { MapCard } from '../features/maps/components/MapCard';
import { OverviewCharts } from '../features/overview/components/OverviewCharts';
import { getFarmSummary } from '../features/overview/utils/farmSummary.ts';
import { WeatherCard } from '../features/weather/components/WeatherCard';

export function OverviewPage() {
  const { t, i18n } = useTranslation();
  const { data: fields } = useSuspenseQuery(fieldQueries.list());
  const { totalArea, attentionCount, criticalCount } = getFarmSummary(fields);
  const summary = fields.length
    ? t('Farm summary', {
        count: fields.length,
        area: totalArea.toLocaleString(i18n.resolvedLanguage, { maximumFractionDigits: 1 }),
        attention: attentionCount,
        critical: criticalCount,
      })
    : t('No fields added yet. Add a field to view its location and monitor crop conditions.');

  return (
    <>
      <PageHeading
        eyebrow=""
        title={t('Overview')}
        description={summary}
        actions={
          <>
            <RouterButton icon={<CalendarDays size={18} />} to="/history">
              {t('Environment')}
            </RouterButton>
            <RouterButton type="primary" icon={<Plus size={19} />} to="/map/add">
              {t('Add field')}
            </RouterButton>
          </>
        }
      />
      <section className="map-weather-grid">
        <MapCard />
        <WeatherCard />
      </section>
      <OverviewCharts />
      <section className="overview-fields" aria-labelledby="overview-fields-title">
        <div className="overview-fields-heading">
          <h2 id="overview-fields-title">{t('Your fields')}</h2>
          <RouterButton
            type="link"
            icon={<ArrowUpRight size={17} />}
            iconPlacement="end"
            to="/fields"
          >
            {t('View all fields')}
          </RouterButton>
        </div>
        <CropFieldCards fields={fields} compact />
      </section>
      <footer className="overview-legal-footer">
        <LegalLinks />
      </footer>
    </>
  );
}
