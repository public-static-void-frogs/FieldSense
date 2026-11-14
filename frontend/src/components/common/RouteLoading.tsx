import { Spin } from 'antd';
import { useTranslation } from 'react-i18next';

export function RouteLoading() {
  const { t } = useTranslation();

  return (
    <div className="app-loading" role="status" aria-label={t('Loading data')}>
      <Spin size="large" />
    </div>
  );
}
