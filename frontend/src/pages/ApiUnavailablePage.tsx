import { Button, Result } from 'antd';
import { useTranslation } from 'react-i18next';

type ApiUnavailablePageProps = {
  retry: () => void;
};

export function ApiUnavailablePage({ retry }: ApiUnavailablePageProps) {
  const { t } = useTranslation();

  return (
    <main className="app-loading" role="alert">
      <Result
        status="warning"
        title={t('API is unavailable')}
        subTitle={t('We cannot connect to the service right now. Please try again in a moment.')}
        extra={
          <Button type="primary" onClick={retry}>
            {t('Try again')}
          </Button>
        }
      />
    </main>
  );
}
