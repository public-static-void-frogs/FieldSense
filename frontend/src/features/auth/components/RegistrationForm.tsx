import { Button, Form, Input, Steps } from 'antd';
import { ArrowLeft, ArrowRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { LocationPicker } from '../../maps/components/LocationPicker.tsx';
import { useRegistrationForm } from '../hooks/useRegistrationForm.ts';
import { AuthError } from './AuthError.tsx';
import { CredentialFields } from './CredentialFields.tsx';

export function RegistrationForm() {
  const { t } = useTranslation();
  const { form, step, next, back, pending, error } = useRegistrationForm();

  return (
    <>
      <Steps
        className="registration-steps"
        current={step}
        size="small"
        responsive={false}
        items={[{ title: t('Account') }, { title: t('Farm and location') }]}
      />
      <AuthError error={error} register />
      <Form
        form={form}
        name="register"
        layout="vertical"
        requiredMark={false}
        disabled={pending}
        initialValues={{ farmName: '' }}
        onFinish={() => {
          void next();
        }}
      >
        {step === 0 && <AccountStep />}
        {step === 1 && <LocationStep disabled={pending} />}
        <div className="registration-actions">
          {step > 0 && (
            <Button icon={<ArrowLeft size={18} />} onClick={back} disabled={pending}>
              {t('Back')}
            </Button>
          )}
          <Button
            type="primary"
            htmlType="submit"
            loading={pending}
            icon={<ArrowRight size={18} />}
            iconPlacement="end"
          >
            {step === 0 ? t('Continue') : t('Create account')}
          </Button>
        </div>
      </Form>
    </>
  );
}

function AccountStep() {
  const { t } = useTranslation();

  return (
    <div className="registration-account-step">
      <Form.Item
        label={t('Full name')}
        name="fullName"
        rules={[
          { required: true, whitespace: true, max: 120, message: t('Enter your full name.') },
        ]}
      >
        <Input autoComplete="name" maxLength={120} />
      </Form.Item>
      <CredentialFields register />
    </div>
  );
}

type LocationStepProps = { disabled: boolean };

function LocationStep({ disabled }: LocationStepProps) {
  const { t } = useTranslation();

  return (
    <>
      <Form.Item label={t('Farm name (optional)')} name="farmName" rules={[{ max: 120 }]}>
        <Input autoComplete="organization" maxLength={120} />
      </Form.Item>
      <Form.Item
        label={t('Current location')}
        name="coordinates"
        rules={[{ required: true, message: t('Choose your location on the map.') }]}
      >
        <LocationPicker disabled={disabled} />
      </Form.Item>
    </>
  );
}
