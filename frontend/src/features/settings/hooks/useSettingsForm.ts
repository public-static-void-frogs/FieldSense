import { useMutation, useQueryClient } from '@tanstack/react-query';
import { App, Form } from 'antd';
import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { authMutations } from '../../../api/auth/auth.mutations.ts';
import { settingsMutations } from '../../../api/settings/settings.mutations.ts';
import type { FarmProfile } from '../../../types/farm/farm.types.ts';
import type { LocationPoint } from '../../../types/maps/map.types.ts';
import { isUnauthorized } from '../../auth/utils/auth.ts';
import { formatLocation } from '../../maps/utils/location.ts';
import {
  formValuesFrom,
  isSectionDirty,
  sectionFields,
  settingsForSection,
  type SettingsSection,
  type SettingsValues,
} from '../utils/settingsForm.ts';

export function useSettingsForm(profile: FarmProfile) {
  const [form] = Form.useForm<SettingsValues>();
  const client = useQueryClient();
  const account = useMutation(authMutations.updateAccount(client));
  const preferences = useMutation(settingsMutations.update(client));
  const { message } = App.useApp();
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const initialValues = formValuesFrom(profile);
  const previousSaved = useRef(initialValues);
  const currentValues =
    Form.useWatch((values: SettingsValues) => values, { form, preserve: true }) ?? initialValues;

  // Refresh untouched fields without overwriting edits in other sections.
  useEffect(() => {
    const saved = formValuesFrom(profile);
    const current = form.getFieldsValue(true);
    for (const key of Object.keys(saved) as (keyof SettingsValues)[]) {
      if (current[key] === previousSaved.current[key] && current[key] !== saved[key]) {
        form.setFieldValue(key, saved[key]);
      }
    }
    previousSaved.current = saved;
  }, [form, profile]);

  function isDirty(section: SettingsSection) {
    return isSectionDirty(section, currentValues, initialValues);
  }

  async function save(section: SettingsSection) {
    if (!isSectionDirty(section, form.getFieldsValue(true), initialValues)) {
      return;
    }
    try {
      await form.validateFields(sectionFields[section]);
    } catch {
      return;
    }
    const values = form.getFieldsValue(true);
    try {
      if (section === 'account') {
        const saved = await account.mutateAsync({ fullName: values.fullName, email: values.email });
        form.setFieldsValue({ fullName: saved.fullName, email: saved.email });
      } else {
        const saved = await preferences.mutateAsync(settingsForSection(section, values, profile));
        for (const key of sectionFields[section]) {
          form.setFieldValue(key, saved[key as keyof typeof saved]);
        }
      }
      void message.success(t('Settings saved.'));
    } catch (error) {
      if (isUnauthorized(error)) {
        navigate('/login?next=%2Fsettings', { replace: true });
        return;
      }
      void message.error(t('Unable to save settings. Please try again.'));
    }
  }

  function reset(section: SettingsSection) {
    form.setFields(
      sectionFields[section].map((key) => ({
        name: key,
        value: initialValues[key],
        touched: false,
        errors: [],
        warnings: [],
      })),
    );
    if (section === 'preferences') {
      void i18n.changeLanguage(profile.language);
    }
  }

  function setLocation(point: LocationPoint) {
    form.setFieldsValue({
      latitude: point.latitude,
      longitude: point.longitude,
      location: formatLocation(point),
    });
  }

  function onValuesChange(changed: Partial<SettingsValues>) {
    if (changed.language) {
      void i18n.changeLanguage(changed.language);
    }
  }

  let coordinates: LocationPoint | undefined;
  if (typeof currentValues.latitude === 'number' && typeof currentValues.longitude === 'number') {
    coordinates = { latitude: currentValues.latitude, longitude: currentValues.longitude };
  }

  return {
    form,
    initialValues,
    coordinates,
    setLocation,
    isDirty,
    save,
    reset,
    onValuesChange,
    pending: account.isPending || preferences.isPending,
  };
}
