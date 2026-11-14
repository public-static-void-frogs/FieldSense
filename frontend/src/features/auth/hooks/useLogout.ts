import { useMutation, useQueryClient } from '@tanstack/react-query';
import { App } from 'antd';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { authMutations } from '../../../api/auth/auth.mutations.ts';
import { isUnauthorized } from '../utils/auth.ts';

export function useLogout() {
  const client = useQueryClient();
  const mutation = useMutation(authMutations.logout(client));
  const navigate = useNavigate();
  const { message } = App.useApp();
  const { t } = useTranslation();

  async function logout() {
    try {
      await mutation.mutateAsync();
    } catch (error) {
      if (!isUnauthorized(error)) {
        void message.error(t('Unable to log out. Please try again.'));
        return;
      }
      await client.cancelQueries();
      client.clear();
    }
    navigate('/login', { replace: true });
  }

  return { logout, pending: mutation.isPending };
}
