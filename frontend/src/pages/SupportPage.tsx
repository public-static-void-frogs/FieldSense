import { useTranslation } from 'react-i18next';
import { PublicPageLayout } from '../features/legal/components/PublicPageLayout.tsx';
import { publicApp } from '../features/legal/constants/publicApp.constants.ts';

export function SupportPage() {
  const { t } = useTranslation();

  return (
    <PublicPageLayout
      title={t('Contact & data requests')}
      description={t('Get help, ask a privacy question, or request removal of your data.')}
    >
      <section className="public-callout">
        <h2>{t('Support and privacy contact')}</h2>
        <a href={`mailto:${publicApp.contactEmail}`}>{publicApp.contactEmail}</a>
        <p>
          {t(
            'Include a short description of your request and the email address you used with the app, if relevant. Never send your password, access tokens, or other credentials.',
          )}
        </p>
      </section>
      <section className="policy-section">
        <h2>{t('Remove data from this demo')}</h2>
        <p>
          {t(
            'Clear this website’s browser data to remove the local language preference and session cookie. Your account and saved settings remain in the database. Contact support to request account or data removal.',
          )}
        </p>
        <p>
          {t(
            'Field changes and other sample data are held in memory and reset when you reload the page. There is no server-side user account or stored Google data to delete in the current prototype.',
          )}
        </p>
      </section>
      <section className="policy-section">
        <h2>{t('Google Calendar and account access')}</h2>
        <p>
          {t(
            'When the optional Google connection becomes available, you can revoke its access through your Google Account connections and remove the dedicated FrogFarmers calendar through Google Calendar settings. Removing access and deleting a calendar are separate actions.',
          )}
        </p>
        <a href="https://myaccount.google.com/connections" target="_blank" rel="noreferrer">
          {t('Manage Google Account connections')}
        </a>
        <p>
          {t(
            'For a request concerning any data retained by FrogFarmers after Google integration is enabled, contact the email above. We may ask you to confirm control of the relevant account before acting on the request.',
          )}
        </p>
      </section>
    </PublicPageLayout>
  );
}
