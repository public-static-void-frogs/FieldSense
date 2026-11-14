# Google OAuth registration and review

## Public app details

- App name: **FrogFarmers**. Keep this spelling and the frog branding consistent in Google Auth Platform and the website.
- Production origin: `https://nasa-fields-demo-app.vercel.app`
- App homepage: `https://nasa-fields-demo-app.vercel.app/about`
- Privacy policy: `https://nasa-fields-demo-app.vercel.app/privacy`
- Terms of service: `https://nasa-fields-demo-app.vercel.app/terms`
- Support and data requests: `https://nasa-fields-demo-app.vercel.app/support`
- Support/privacy email: `olehzpr@gmail.com`. Google requires the selected support email to be a permitted account or managed group in the project; choose the corresponding account in the console.
- Public identity: FrogFarmers project team. The app does not claim to be a registered company or use the fictional farm profile as its operator.
- Branding image: `public/frog-farmer.png`; use a square PNG that meets Google's current upload limits.

These pages are outside the farm layout, need no login or query-backed farm data,
and have English/Ukrainian language selection. The root demo, login page, and Help
page also link to the public information. `vercel.json` supplies the SPA rewrite
needed for direct visits to the public URLs.

## Registration steps outside this repository

1. Deploy the updated build to the production project. Check that its public URLs are accessible without Vercel authentication or deployment protection. The local changes do not deploy the website.
2. Verify ownership of the authorized domain using a Google Search Console property associated with the Google Cloud project owner/editor. For the hosted project, use `nasa-fields-demo-app.vercel.app`, not the parent `vercel.app` domain. A custom domain can also be used if it is owned and verified; update every URL consistently if the domain changes.
3. Complete the Branding page with the app name, support email, homepage, privacy policy, terms, and developer contact email. The privacy link must exactly match the website's privacy link.
4. Configure the OAuth audience and test users while the integration is being developed. Enable the Google Calendar API in the same project.
5. Create the appropriate OAuth client. For the browser client, the authorized JavaScript origin is `https://nasa-fields-demo-app.vercel.app`, without a path. Register an HTTPS redirect URI only after the authentication flow and callback endpoint have been implemented; there is no OAuth callback endpoint in this prototype yet.
6. Store a client secret only on a backend. Never put a secret or refresh token in Vite environment variables, public assets, source code, or browser local storage. A public browser client ID is not a client secret.

If Search Console provides an HTML verification file, place the exact supplied
file in `public/` and deploy it, or use another verification method available for
the property. Do not invent a verification token. Follow Google's instructions
for the selected property and the domain accepted by the consent-screen console.

## Intended permissions and feature boundary

Google connections are **not implemented** by this change. The public pages describe
them as planned and describe the actual demo's storage separately. No OAuth buttons,
tokens, fake synchronization, or simulated Google authorization have been added.

The intended integration is:

- Sign-in: `openid`, `email`, and `profile`, to identify the user. This may return a Google subject identifier, email address, display name, and profile image.
- Optional Calendar connection: `https://www.googleapis.com/auth/calendar.app.created`, to create a dedicated FrogFarmers calendar and manage events in app-created calendars. Ask for this separately when the user chooses to connect Calendar.
- No Gmail, Drive, Contacts, broad `calendar`, or read/write access to events in pre-existing personal/work calendars is needed for this design.

The Calendar scope permits reading and modifying events in calendars created by
the app. The eventual implementation must keep its behavior limited to the
user-selected field-plan exports disclosed in the privacy policy. Do not silently
expand to reading unrelated calendar events. Any change in feature scope requires
reviewing permissions and updating the disclosures before requesting new access.

## Work required before scope verification

Registering a client and publishing policy pages alone does not establish that
Google will verify the app. Do not submit requests for permissions for a feature
that only exists as a future plan.

Before submitting the Calendar integration for verification:

- Implement real Google sign-in, token verification, the Calendar consent flow, and working calendar creation/export. Handle declined consent, expired/revoked access, and reconnecting.
- Decide and implement actual token/session storage, account data storage, access controls, retention periods, backups if any, and data deletion. Update the privacy notice to describe those facts and any processors. The current notice deliberately makes no claims about nonexistent backend security or retention.
- Make the promised Limited Use practices true: use Google data only for the disclosed sign-in/export functions; do not sell it, use it for advertising or general-purpose AI training, or feed it into agronomy predictions.
- Provide a working disconnect flow. Explain that revoking access does not delete existing Google Calendar events; support calendar removal and data requests separately.
- In Google Auth Platform, check the classification of the exact requested Calendar scope. Complete any required sensitive-scope review, with a justification and a demonstration video showing the actual consent flow and the feature that uses each permission. A video of an unconnected demo is insufficient.
- Confirm the production behavior, consent-screen scopes, homepage, and privacy disclosures agree. Replace planned-feature wording only when the corresponding feature and data-handling commitments are implemented.

## References

- [Google OAuth app branding and website requirements](https://support.google.com/cloud/answer/15549049?hl=en)
- [Google Calendar authorization scopes](https://developers.google.com/workspace/calendar/api/auth)
- [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy)
- [Sensitive scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification)
- [Vite SPA hosting on Vercel](https://vercel.com/docs/frameworks/frontend/vite#using-vite-to-make-spas)

Google documentation was consulted on October 28, 2026. Scope classification and
console requirements should be checked again at submission time.
