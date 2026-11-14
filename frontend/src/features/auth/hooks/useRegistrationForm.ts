import { Form } from 'antd';
import { useState } from 'react';
import { ApiError } from '../../../api/core/http.ts';
import type { LocationPoint } from '../../../types/maps/map.types.ts';
import { formatLocation } from '../../maps/utils/location.ts';
import { useAuthForm } from './useAuthForm.ts';

type RegistrationValues = {
  fullName: string;
  email: string;
  password: string;
  confirmPassword: string;
  farmName?: string;
  coordinates?: LocationPoint;
};

export function useRegistrationForm() {
  const [form] = Form.useForm<RegistrationValues>();
  const [step, setStep] = useState(0);
  const auth = useAuthForm(true);

  async function next() {
    if (step === 0) {
      setStep(1);
      return;
    }
    const values = form.getFieldsValue(true);
    if (!values.coordinates) {
      return;
    }
    try {
      await auth.submit({
        fullName: values.fullName,
        email: values.email,
        password: values.password,
        farmName: values.farmName?.trim() || '',
        location: formatLocation(values.coordinates),
        latitude: values.coordinates.latitude,
        longitude: values.coordinates.longitude,
        language: 'en',
      });
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setStep(0);
      }
    }
  }

  return { form, step, next, back: () => setStep(0), pending: auth.pending, error: auth.error };
}
