import { useSuspenseQuery } from '@tanstack/react-query';
import { Avatar, Button, Card, Form, Input, InputNumber, Select, Space, Typography } from 'antd';
import { Camera, LogOut } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { farmQueries } from '../api/farm/farm.queries.ts';
import { useLogout } from '../features/auth/hooks/useLogout.ts';
import { useSettingsForm } from '../features/settings/hooks/useSettingsForm.ts';
import type { SettingsSection } from '../features/settings/utils/settingsForm.ts';
import { LocationPicker } from '../features/maps/components/LocationPicker.tsx';
import '../styles/settings.css';

export function SettingsPage() {
  const { t } = useTranslation();
  const { data: preferences } = useSuspenseQuery(farmQueries.profile());
  const settings = useSettingsForm(preferences);
  const { logout, pending: logoutPending } = useLogout();

  return (
    <div className="settings-page">
      <div className="page-heading">
        <Typography.Title level={1}>{t('Settings')}</Typography.Title>
      </div>
      <Form
        layout="vertical"
        requiredMark={false}
        form={settings.form}
        disabled={settings.pending}
        onValuesChange={settings.onValuesChange}
        initialValues={settings.initialValues}
      >
        <div className="settings-grid">
          <Card
            title={t('Account information')}
            extra={
              <SectionActions
                section="account"
                label={t('Account information')}
                settings={settings}
              />
            }
          >
            <div className="settings-profile-photo">
              <Avatar size={72}>{preferences.initials}</Avatar>
              <div>
                <Typography.Text strong>{t('Profile photo')}</Typography.Text>
                <Button icon={<Camera size={17} />} disabled>
                  {t('Change photo')}
                </Button>
              </div>
              <Button
                className="settings-logout"
                icon={<LogOut size={18} />}
                onClick={() => {
                  void logout();
                }}
                loading={logoutPending}
              >
                {t('Log out')}
              </Button>
            </div>
            <Form.Item
              label={t('Full name')}
              name="fullName"
              rules={[
                { required: true, whitespace: true, max: 120, message: t('Enter your full name.') },
              ]}
            >
              <Input autoComplete="name" />
            </Form.Item>
            <Form.Item
              label={t('Email address')}
              name="email"
              rules={[
                {
                  required: true,
                  type: 'email',
                  max: 254,
                  message: t('Enter a valid email address.'),
                },
              ]}
            >
              <Input type="email" autoComplete="email" />
            </Form.Item>
            <div className="settings-account-role">
              <Typography.Text type="secondary">{t('Account role')}</Typography.Text>
              <Typography.Text>{t(preferences.role)}</Typography.Text>
            </div>
          </Card>
          <Card
            title={t('Application preferences')}
            extra={
              <SectionActions
                section="preferences"
                label={t('Application preferences')}
                settings={settings}
              />
            }
          >
            <Form.Item label={t('Measurement units')} name="units">
              <Select
                options={[
                  { value: 'metric', label: t('Metric (ha, °C, mm)') },
                  { value: 'imperial', label: t('Imperial (ac, °F, in)') },
                ]}
              />
            </Form.Item>
            <Form.Item label={t('Application language')} name="language">
              <Select
                options={[
                  { value: 'en', label: t('English') },
                  { value: 'uk', label: t('Українська') },
                ]}
              />
            </Form.Item>
            <Form.Item label={t('Color theme')} name="theme">
              <Select
                options={[
                  { value: 'light', label: t('Light') },
                  { value: 'dark', label: t('Dark') },
                  { value: 'system', label: t('System default') },
                ]}
              />
            </Form.Item>
            <Form.Item
              label={t('Session lifetime (hours)')}
              name="sessionLifetimeHours"
              extra={t('Default: 24 hours. Applies to this session and future logins.')}
              rules={[
                {
                  required: true,
                  type: 'integer',
                  min: 1,
                  max: 720,
                  message: t('Choose 1–720 hours.'),
                },
              ]}
            >
              <InputNumber min={1} max={720} precision={0} />
            </Form.Item>
          </Card>
          <Card
            title={t('Farm information')}
            extra={
              <SectionActions section="farm" label={t('Farm information')} settings={settings} />
            }
          >
            <div className="settings-location-grid">
              <Form.Item label={t('Farm name (optional)')} name="farmName" rules={[{ max: 120 }]}>
                <Input />
              </Form.Item>
              <Form.Item label={t('Growing season')} name="season">
                <Select
                  options={preferences.availableSeasons.map((value) => ({ value, label: value }))}
                />
              </Form.Item>
              <Form.Item
                label={t('Time zone')}
                name="timeZone"
                rules={[
                  { required: true, whitespace: true, message: t('Enter a valid time zone.') },
                ]}
              >
                <Input placeholder="Europe/Kyiv" />
              </Form.Item>
            </div>
          </Card>
          <Card
            title={t('Current location')}
            className="settings-location-card"
            extra={
              <SectionActions
                section="location"
                label={t('Current location')}
                settings={settings}
              />
            }
          >
            <Form.Item name="location" hidden>
              <Input />
            </Form.Item>
            <Form.Item name="latitude" hidden>
              <Input />
            </Form.Item>
            <Form.Item name="longitude" hidden>
              <Input />
            </Form.Item>
            <LocationPicker
              value={settings.coordinates}
              onChange={settings.setLocation}
              disabled={settings.pending}
              autoLocate={false}
            />
          </Card>
        </div>
      </Form>
    </div>
  );
}

type SectionActionsProps = {
  section: SettingsSection;
  label: string;
  settings: ReturnType<typeof useSettingsForm>;
};

function SectionActions({ section, label, settings }: SectionActionsProps) {
  const { t } = useTranslation();

  return (
    <Space size={8}>
      <Button
        disabled={settings.pending || !settings.isDirty(section)}
        onClick={() => settings.reset(section)}
        aria-label={t('Clear {{value0}}', { value0: label })}
      >
        {t('Clear')}
      </Button>
      <Button
        type="primary"
        loading={settings.pending}
        disabled={settings.pending || !settings.isDirty(section)}
        onClick={() => {
          void settings.save(section);
        }}
        aria-label={t('Save {{value0}}', { value0: label })}
      >
        {t('Save')}
      </Button>
    </Space>
  );
}
