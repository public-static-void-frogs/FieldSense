import { Trans, useTranslation } from 'react-i18next';
import { publicApp } from '../constants/publicApp.constants.ts';

export type PolicySection = {
  id: string;
  title: string;
  paragraphs: string[];
};

type PolicyDocumentProps = { sections: PolicySection[] };

export function PolicyDocument({ sections }: PolicyDocumentProps) {
  const { t, i18n } = useTranslation();

  return (
    <article className="policy-document">
      <p className="policy-updated">
        {t('Last updated: {{date}}', {
          date: new Date(`${publicApp.policyUpdated}T12:00:00`).toLocaleDateString(
            i18n.resolvedLanguage,
            { year: 'numeric', month: 'long', day: 'numeric' },
          ),
        })}
      </p>
      <nav className="policy-contents" aria-label={t('On this page')}>
        {sections.map((section) => (
          <a key={section.id} href={`#${section.id}`}>
            {t(section.title)}
          </a>
        ))}
      </nav>
      {sections.map((section) => (
        <section key={section.id} id={section.id} className="policy-section">
          <h2>{t(section.title)}</h2>
          {section.paragraphs.map((paragraph) => (
            <p key={paragraph}>{t(paragraph)}</p>
          ))}
        </section>
      ))}
      <p>
        <Trans
          i18nKey="For questions or data requests, email <contact>{{email}}</contact>."
          values={{ email: publicApp.contactEmail }}
          components={{ contact: <a href={`mailto:${publicApp.contactEmail}`} /> }}
        />
      </p>
    </article>
  );
}
