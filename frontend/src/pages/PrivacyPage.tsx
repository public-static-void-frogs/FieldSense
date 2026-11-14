import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { PolicyDocument } from '../features/legal/components/PolicyDocument.tsx';
import { PublicPageLayout } from '../features/legal/components/PublicPageLayout.tsx';
import { publicApp } from '../features/legal/constants/publicApp.constants.ts';
import { privacySections } from '../features/legal/constants/policies.constants.ts';

export function PrivacyPage() {
  const { t } = useTranslation();

  return (
    <PublicPageLayout
      title={t('Privacy policy')}
      description={t(
        'How FrogFarmers handles demo data, browser storage, and the planned Google connection.',
      )}
    >
      <PolicyDocument sections={privacySections} />
      <section className="policy-section">
        <h2>{t('Planned Google permissions')}</h2>
        <p>
          {t(
            'Google sign-in is planned to request only your basic account identity: a Google account identifier, email address, name, and profile picture. It is separate from Calendar permission.',
          )}
        </p>
        <ul>
          {publicApp.signInScopes.map((scope) => (
            <li key={scope}>
              <code>{scope}</code>
            </li>
          ))}
        </ul>
        <p>
          {t(
            'The optional Calendar connection is planned to use the permission below to create a dedicated FrogFarmers calendar and manage events on calendars created by the app. It does not grant access to events in your existing personal or work calendars.',
          )}
        </p>
        <p>
          <code className="scope-value">{publicApp.calendarScope}</code>
        </p>
        <p>
          {t(
            'Calendar event information is limited to the field-plan details you choose to export, such as the action title, date and time, description, and field name. Field names may be personal or sensitive; review them before exporting.',
          )}
        </p>
        <p>
          {t(
            'The current prototype does not request these permissions. We will update this notice with the actual storage, retention, security, and service-provider details before enabling Google connections.',
          )}
        </p>
      </section>
      <p>
        <a
          href="https://developers.google.com/terms/api-services-user-data-policy"
          target="_blank"
          rel="noreferrer"
        >
          {t('Google API Services User Data Policy')}
        </a>
      </p>
      <section className="policy-section">
        <h2>{t('Disconnect and request deletion')}</h2>
        <p>
          {t(
            'You can review or revoke an app’s Google access in your Google Account connections. Revoking access does not automatically delete events or calendars already created in Google Calendar.',
          )}
        </p>
        <p>
          <a href="https://myaccount.google.com/connections" target="_blank" rel="noreferrer">
            {t('Manage Google Account connections')}
          </a>
        </p>
        <p>
          <Link to="/support">{t('View storage removal and data-request instructions')}</Link>
        </p>
      </section>
    </PublicPageLayout>
  );
}
