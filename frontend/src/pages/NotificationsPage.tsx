import { useSuspenseQuery } from '@tanstack/react-query';
import { Alert, Card, Empty, Space } from 'antd';
import { ArrowRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { notificationQueries } from '../api/notifications/notifications.queries.ts';
import { WeatherAdvisories } from '../features/weather/components/WeatherAdvisories';
import { PageHeading } from '../components/common/PageHeading';
import { RouterButton } from '../components/common/RouterButton';

export function NotificationsPage() {
  const { t } = useTranslation();
  const { data: notifications } = useSuspenseQuery(notificationQueries.list());

  return (
    <>
      <PageHeading
        title={t('A heads-up from your farm.')}
        description={t('The field updates and weather changes worth keeping an eye on.')}
        eyebrow={t('NOTIFICATIONS')}
      />
      <Space orientation="vertical" size={20} className="full-width">
        <WeatherAdvisories />
        {notifications.map((notification) => (
          <Card key={notification.id}>
            <Alert
              type={notification.severity}
              showIcon
              title={t(notification.title, { value0: notification.fieldName })}
              description={t(notification.description)}
            />
            <RouterButton
              className="notification-link"
              type="link"
              to={notification.kind === 'field' ? `/fields/${notification.fieldId}` : '/history'}
            >
              {t(notification.kind === 'field' ? 'View field' : 'View weather history')}{' '}
              <ArrowRight size={18} />
            </RouterButton>
          </Card>
        ))}
        {!notifications.some((notification) => notification.kind === 'field') && (
          <Card>
            <Empty description={t('Your fields are looking good. You’re all caught up.')} />
          </Card>
        )}
      </Space>
    </>
  );
}
