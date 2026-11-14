import { useTranslation } from 'react-i18next';
import { PolicyDocument } from '../features/legal/components/PolicyDocument.tsx';
import { PublicPageLayout } from '../features/legal/components/PublicPageLayout.tsx';
import { termsSections } from '../features/legal/constants/policies.constants.ts';

export function TermsPage() {
  const { t } = useTranslation();

  return (
    <PublicPageLayout
      title={t('Terms of service')}
      description={t('Conditions for using the FrogFarmers prototype.')}
    >
      <PolicyDocument sections={termsSections} />
    </PublicPageLayout>
  );
}
