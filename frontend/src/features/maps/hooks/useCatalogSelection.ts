import { useMutation, useQueryClient } from '@tanstack/react-query';
import { App } from 'antd';
import { useTranslation } from 'react-i18next';
import { fieldMutations } from '../../../api/fields/fields.mutations.ts';

export function useCatalogSelection() {
  const client = useQueryClient();
  const { message } = App.useApp();
  const { t } = useTranslation();
  const selection = useMutation(fieldMutations.select(client));
  const removal = useMutation(fieldMutations.remove(client));
  async function toggle(id: string, selected: boolean) {
    try {
      if (selected) {
        await removal.mutateAsync(id);
        message.success(t('Field removed from my fields'));
      } else {
        await selection.mutateAsync(id);
        message.success(t('Field added to my fields'));
      }
    } catch {
      message.error(t('Unable to save changes'));
    }
  }
  return { toggle, isPending: selection.isPending || removal.isPending };
}
