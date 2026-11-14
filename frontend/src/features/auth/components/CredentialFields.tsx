import { Form, Input } from 'antd';
import { useTranslation } from 'react-i18next';

type CredentialFieldsProps = { register?: boolean };

export function CredentialFields({ register = false }: CredentialFieldsProps) {
  const { t } = useTranslation();

  return (
    <>
      <Form.Item
        label={t('Email address')}
        name="email"
        rules={[
          { required: true, message: t('Enter your email address.') },
          { type: 'email', max: 254, message: t('Enter a valid email address.') },
        ]}
      >
        <Input type="email" autoComplete="username" autoCapitalize="none" spellCheck={false} />
      </Form.Item>
      <Form.Item
        label={t('Password')}
        name="password"
        rules={[
          { required: true, message: t('Enter your password.') },
          ...(register
            ? [{ min: 8, max: 128, message: t('Use 8–128 characters for your password.') }]
            : []),
        ]}
      >
        <Input.Password autoComplete={register ? 'new-password' : 'current-password'} />
      </Form.Item>
      {register && (
        <Form.Item
          label={t('Confirm password')}
          name="confirmPassword"
          dependencies={['password']}
          rules={[
            { required: true, message: t('Confirm your password.') },
            ({ getFieldValue }) => ({
              validator(_, value) {
                if (!value || getFieldValue('password') === value) {
                  return Promise.resolve();
                }
                return Promise.reject(new Error(t('Passwords do not match.')));
              },
            }),
          ]}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
      )}
    </>
  );
}
