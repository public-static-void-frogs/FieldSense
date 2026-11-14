import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate } from 'react-router-dom';
import type { LoginInput, RegisterInput } from '../../../api/auth/auth.api.ts';
import { authMutations } from '../../../api/auth/auth.mutations.ts';
import { returnPath } from '../utils/auth.ts';

export function useAuthForm(register: boolean) {
  const client = useQueryClient();
  const login = useMutation(authMutations.login(client));
  const registration = useMutation(authMutations.register(client));
  const navigate = useNavigate();
  const { search } = useLocation();
  const { i18n } = useTranslation();
  const mutation = register ? registration : login;

  async function submit(values: LoginInput | RegisterInput) {
    if (register) {
      await registration.mutateAsync({
        email: values.email,
        password: values.password,
        fullName: (values as RegisterInput).fullName,
        farmName: (values as RegisterInput).farmName,
        location: (values as RegisterInput).location,
        latitude: (values as RegisterInput).latitude,
        longitude: (values as RegisterInput).longitude,
        language: i18n.resolvedLanguage === 'uk' ? 'uk' : 'en',
      });
    } else {
      await login.mutateAsync(values);
    }
    navigate(returnPath(search), { replace: true });
  }

  return { submit, pending: mutation.isPending, error: mutation.error };
}
