import { useSuspenseQuery } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { fieldQueries } from '../api/fields/fields.queries.ts';
import { PageHeading } from '../components/common/PageHeading';
import { RouterButton } from '../components/common/RouterButton';
import { CropFieldCards } from '../features/fields/components/CropFieldCards.tsx';
import { useDemoMode } from '../features/demo/hooks/useDemoMode.ts';

export function FieldsPage() {
  const { t } = useTranslation();
  const demo = useDemoMode();
  const { data: fields } = useSuspenseQuery(fieldQueries.list());

  return (
    <>
      <PageHeading
        eyebrow=""
        title={t('Manage your fields')}
        actions={
          !demo && (
            <RouterButton type="primary" icon={<Plus size={19} />} to="/map/add">
              {t('Add')}
            </RouterButton>
          )
        }
      />
      <CropFieldCards fields={fields} />
    </>
  );
}
