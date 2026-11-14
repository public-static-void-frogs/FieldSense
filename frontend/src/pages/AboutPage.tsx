import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { PublicPageLayout } from '../features/legal/components/PublicPageLayout.tsx';
import { publicApp } from '../features/legal/constants/publicApp.constants.ts';

export function AboutPage() {
  const { t } = useTranslation();

  return (
    <PublicPageLayout
      title={t('A clearer plan for your fields.')}
      description={t(
        'Weather uses live model data for your saved location. Field records and agronomic recommendations remain illustrative.',
      )}
    >
      <section className="public-feature-grid" aria-label={t('What FrogFarmers does')}>
        <Feature
          title={t('Understand your fields')}
          description={t(
            'Explore field locations, crop health, soil properties, moisture, and environmental history in one place.',
          )}
        />
        <Feature
          title={t('Compare crop rotations')}
          description={t(
            'Review illustrative rotation strategies, their assumptions, and the checks needed before planting.',
          )}
        />
        <Feature
          title={t('Plan field work')}
          description={t(
            'Review proposed soil checks, irrigation, planting, and harvest actions in the built-in calendar.',
          )}
        />
      </section>
      <section className="public-callout">
        <h2>{t('Google sign-in and Calendar connection')}</h2>
        <p>
          {t(
            'We are preparing Google sign-in and an optional connection that exports field-plan actions to a dedicated FrogFarmers calendar in your Google Account.',
          )}
        </p>
        <p>
          {t(
            'These Google features are not enabled in the current demo. The demo does not request Google permissions, receive Google account data, or access your Google Calendar.',
          )}
        </p>
        <Link to="/privacy">{t('Read about Google data and permissions')}</Link>
      </section>
      <section className="policy-section">
        <h2>{t('Who we are')}</h2>
        <p>
          {t(
            'FrogFarmers is a prototype built by the FrogFarmers project team. It demonstrates a field-planning workflow with sample agronomy data and illustrative predictions.',
          )}
        </p>
        <p>
          {t('Support and privacy contact')}:{' '}
          <a href={`mailto:${publicApp.contactEmail}`}>{publicApp.contactEmail}</a>
        </p>
        <Link className="public-primary-link" to="/">
          {t('Explore the demo')}
        </Link>
      </section>
    </PublicPageLayout>
  );
}

type FeatureProps = { title: string; description: string };

function Feature({ title, description }: FeatureProps) {
  return (
    <article className="public-feature">
      <h2>{title}</h2>
      <p>{description}</p>
    </article>
  );
}
