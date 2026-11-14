import { Button, Result } from 'antd';
import { useTranslation } from 'react-i18next';
import { isRouteErrorResponse, useRevalidator, useRouteError } from 'react-router-dom';
import { RouterButton } from '../components/common/RouterButton';

export function RouteErrorPage() {
  const { t } = useTranslation();
  const error = useRouteError();
  const revalidator = useRevalidator();
  const notFound = !error || (isRouteErrorResponse(error) && error.status === 404);

  return (
    <Result
      status={notFound ? '404' : 'error'}
      title={t(notFound ? 'Page not found' : 'Unable to load data')}
      extra={
        notFound ? (
          <RouterButton type="primary" to="/">
            {t('Back to overview')}
          </RouterButton>
        ) : (
          <Button
            type="primary"
            loading={revalidator.state === 'loading'}
            onClick={() => void revalidator.revalidate()}
          >
            {t('Try again')}
          </Button>
        )
      }
    />
  );
}
