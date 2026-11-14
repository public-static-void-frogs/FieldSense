import { Alert, Button, Empty, Space, Spin } from 'antd';
import { useTranslation } from 'react-i18next';
import { RouterButton } from '../../../components/common/RouterButton';

type WeatherStatusProps = {
  hasLocation: boolean;
  pending: boolean;
  error: unknown;
  retry: () => void;
};

export function WeatherStatus({ hasLocation, pending, error, retry }: WeatherStatusProps) {
  const { t } = useTranslation();

  if (!hasLocation) {
    return (
      <Space orientation="vertical">
        <Empty description={t('Choose your farm location in Settings to load weather.')} />
        <RouterButton to="/settings">{t('Open Settings')}</RouterButton>
      </Space>
    );
  }
  if (pending) {
    return <Spin description={t('Loading weather…')} />;
  }
  if (error) {
    return (
      <Alert
        type="warning"
        showIcon
        title={t('Weather is temporarily unavailable')}
        description={t('Please try again. No sample weather is shown.')}
        action={<Button onClick={retry}>{t('Try again')}</Button>}
      />
    );
  }

  return <Empty description={t('No weather readings available for this period.')} />;
}
