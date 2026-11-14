import { Select } from 'antd';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { publicApp } from '../constants/publicApp.constants.ts';
import { LegalLinks } from './LegalLinks.tsx';
import './legal.css';

type PublicPageLayoutProps = {
  title: string;
  description?: string;
  children: ReactNode;
};

export function PublicPageLayout({ title, description, children }: PublicPageLayoutProps) {
  const { t, i18n } = useTranslation();

  return (
    <div className="public-page">
      <header className="public-header">
        <Link to="/about" className="public-brand" aria-label={t('FrogFarmers home')}>
          <img src="/frog-farmer.png" width={40} height={40} alt="" />
          {publicApp.name}
        </Link>
        <div className="public-header-actions">
          <Select
            aria-label={t('Language')}
            value={i18n.resolvedLanguage ?? 'en'}
            onChange={(language) => void i18n.changeLanguage(language)}
            options={[
              { value: 'en', label: 'English' },
              { value: 'uk', label: 'Українська' },
            ]}
          />
          <Link to="/">{t('Explore the demo')}</Link>
        </div>
      </header>
      <main className="public-content" id="main-content">
        <header className="public-intro">
          <p className="public-eyebrow">{publicApp.name}</p>
          <h1>{title}</h1>
          {description && <p>{description}</p>}
        </header>
        {children}
      </main>
      <footer className="public-footer">
        <LegalLinks />
        <a href={`mailto:${publicApp.contactEmail}`}>{publicApp.contactEmail}</a>
      </footer>
    </div>
  );
}
