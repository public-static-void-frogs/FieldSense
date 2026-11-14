import type { PolicySection } from '../components/PolicyDocument.tsx';

export const privacySections: PolicySection[] = [
  {
    id: 'operator',
    title: 'Who is responsible',
    paragraphs: [
      'FrogFarmers is operated as a project prototype by the FrogFarmers team. Contact olehzpr@gmail.com for support or privacy requests.',
    ],
  },
  {
    id: 'demo-data',
    title: 'Data in the current demo',
    paragraphs: [
      'Account details and settings are stored in the application database. Weather uses Open-Meteo; fields and agronomic recommendations remain illustrative demo data. Google is not connected.',
      'Registration and login send your credentials to the application API. Passwords are stored as Argon2 hashes. Field edits and planning decisions are shared demo state and reset when the API restarts.',
    ],
  },
  {
    id: 'browser-storage',
    title: 'Browser storage and retention',
    paragraphs: [
      'A session token is stored in an HttpOnly cookie. Sessions last 24 hours by default; you can change the lifetime in Settings. Your selected language is also cached in this browser. Account settings persist in the database until changed or removed.',
      'The app does not store Google tokens, Google profile information, or Google Calendar events. Reloading the browser preserves your account and settings. Logging out clears the session cookie and revokes all existing sessions for your account.',
    ],
  },
  {
    id: 'google-use',
    title: 'Purpose of the planned Google connection',
    paragraphs: [
      'Google sign-in is intended only to identify you and associate you with your FrogFarmers account. Calendar access is optional and intended only to export field-plan actions you select to a dedicated FrogFarmers calendar.',
      'We will not use Google user data for advertising, sell it to data brokers, or use it to train general-purpose AI or machine-learning models. Google account and Calendar data will not be used to generate agronomic predictions.',
      'Any future access to or transfer of Google user data must follow the Google API Services User Data Policy, including its Limited Use restrictions.',
    ],
  },
  {
    id: 'sharing',
    title: 'Data sharing and service providers',
    paragraphs: [
      'The backend sends your saved coordinates, time zone and unit preferences to Open-Meteo to retrieve weather. It does not send your account name, email or password.',
      'The current demo sends no Google user data to any third party. If you later connect Google Calendar, exported field-plan information will be sent to Google to provide the calendar feature you request.',
      'Vercel delivers this website. Map imagery is requested from Esri, which receives technical connection information and the displayed map area. During registration, your browser asks permission to use your position to initialize the location map. You can decline and select a point manually. Selected coordinates are saved with your account settings when you create the account.',
    ],
  },
  {
    id: 'security',
    title: 'Security and changes to this notice',
    paragraphs: [
      'Use the published HTTPS website. Do not send passwords or authorization tokens to our support email. No Google credentials or tokens are currently collected by this prototype.',
      'Before Google connections are enabled, this policy will be updated to describe the actual storage, retention periods, security controls, and service providers. If data use changes, the updated practices will be disclosed before new access is requested.',
    ],
  },
];

export const termsSections: PolicySection[] = [
  {
    id: 'service',
    title: 'About this service',
    paragraphs: [
      'FrogFarmers combines live weather model data with illustrative field management and crop-rotation planning. Google sign-in and Calendar export are not available in the current prototype.',
    ],
  },
  {
    id: 'responsible-use',
    title: 'Responsible use',
    paragraphs: [
      'Use the app lawfully and do not attempt to access other people’s accounts, disrupt the service, or submit content you are not entitled to use. Use a unique password and avoid confidential production records in the demo.',
    ],
  },
  {
    id: 'decisions',
    title: 'Field decisions and limitations',
    paragraphs: [
      'Weather forecasts are model estimates and may differ from local conditions. Agronomic recommendations remain illustrative and are not professional advice or a guarantee of yields. Verify decisions using local observations and qualified advice.',
    ],
  },
  {
    id: 'google-calendar',
    title: 'Optional Google Calendar connection',
    paragraphs: [
      'If the Calendar feature becomes available, you will choose whether to connect Google and which field-plan actions to export. Review event details and any field names before exporting. You can revoke Google access and manage the dedicated calendar in your Google Account.',
      'Disconnecting an app does not itself remove events or calendars already stored by Google. Google services are also governed by Google’s own terms and privacy policies.',
    ],
  },
  {
    id: 'availability',
    title: 'Availability and updates',
    paragraphs: [
      'The prototype may change or become unavailable. Demo field edits reset when the API restarts. Clearing browser data signs you out; account settings remain in the database. Keep your own copies of important plans.',
      'Changes to these terms will be published on this page with an updated date. Questions about the service or these terms can be sent to the support email below.',
    ],
  },
];
