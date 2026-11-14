import { Button, Form } from 'antd';
import { ArrowRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAuthForm } from '../hooks/useAuthForm.ts';
import { AuthError } from './AuthError.tsx';
import { CredentialFields } from './CredentialFields.tsx';

export function LoginForm() {
  const { t } = useTranslation();
  const { submit, pending, error } = useAuthForm(false);

  return (
    <>
      <AuthError error={error} />
      <Form
        name="login"
        layout="vertical"
        requiredMark={false}
        disabled={pending}
        onFinish={(values) => {
          void submit(values).catch(() => {});
        }}
      >
        <CredentialFields />
        <Button
          type="primary"
          htmlType="submit"
          loading={pending}
          block
          icon={<ArrowRight size={18} />}
          iconPlacement="end"
        >
          {t('Log in')}
        </Button>
      </Form>
    </>
  );
}
