import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

export function LegalLinks() {
  const { t } = useTranslation();

  return (
    <nav className="legal-links" aria-label={t('About, privacy and support')}>
      <Link to="/about">{t('About FrogFarmers')}</Link>
      <Link to="/privacy">{t('Privacy policy')}</Link>
      <Link to="/terms">{t('Terms of service')}</Link>
      <Link to="/support">{t('Contact & data requests')}</Link>
    </nav>
  );
}
