import { useTranslation } from 'react-i18next';
import { LegalLinks } from './LegalLinks.tsx';
import './legal.css';

export function ProductNotice() {
  const { t } = useTranslation();

  return (
    <section className="product-notice" aria-label={t('About FrogFarmers')}>
      <p>
        {t(
          'Weather uses live model data for your saved location. Field records and agronomic recommendations remain illustrative.',
        )}
      </p>
      <LegalLinks />
    </section>
  );
}
