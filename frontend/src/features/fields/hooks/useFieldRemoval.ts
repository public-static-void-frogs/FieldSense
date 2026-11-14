import { useMutation, useQueryClient } from '@tanstack/react-query';
import { App } from 'antd';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { fieldMutations } from '../../../api/fields/fields.mutations.ts';

export function useFieldRemoval(fieldId: string) {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { message } = App.useApp();
  const client = useQueryClient();
  const { mutateAsync: removeField, isPending: isRemovingField } = useMutation(
    fieldMutations.remove(client),
  );
  const [confirmRemove, setConfirmRemove] = useState(false);
  async function handleRemove() {
    try {
      await removeField(fieldId);
      message.success(t('Field removed'));
      navigate('/map');
    } catch {
      message.error(t('Unable to save changes'));
    }
  }

  return { confirmRemove, setConfirmRemove, isRemovingField, handleRemove };
}
