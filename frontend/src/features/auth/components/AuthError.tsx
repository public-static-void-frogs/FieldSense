import { Alert } from 'antd';
import { useTranslation } from 'react-i18next';
import { ApiError } from '../../../api/core/http.ts';

type AuthErrorProps = { error: Error | null; register?: boolean };

export function AuthError({ error, register = false }: AuthErrorProps) {
  const { t } = useTranslation();
  if (!error) {
    return null;
  }
  let title = t('Unable to sign in. Please try again.');
  if (error instanceof ApiError && error.status === 401) {
    title = t('Invalid email or password.');
  } else if (error instanceof ApiError && error.status === 409) {
    title = t('An account with this email already exists.');
  } else if (register) {
    title = t('Unable to create account. Please try again.');
  }

  return <Alert type="error" title={title} showIcon role="alert" />;
}
