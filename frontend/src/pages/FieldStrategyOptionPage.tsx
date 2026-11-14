import { useSuspenseQueries } from '@tanstack/react-query';
import { Card, Result, Typography } from 'antd';
import { ArrowLeft } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useLoaderData } from 'react-router-dom';
import { fieldQueries } from '../api/fields/fields.queries.ts';
import type { StrategyOptionRouteData } from '../app/route-loaders.ts';
import { PageHeading } from '../components/common/PageHeading';
import { RouterButton } from '../components/common/RouterButton';

export function FieldStrategyOptionPage() {
  const { t } = useTranslation();
  const { fieldId, strategyId } = useLoaderData<StrategyOptionRouteData>();
  const [{ data: field }, { data: strategies }] = useSuspenseQueries({
    queries: [fieldQueries.byId(fieldId), fieldQueries.strategyOptions()],
  });
  const strategy = strategies.find(({ id }) => id === strategyId);
  const fieldPath = `/fields/${fieldId}`;

  if (!field || !strategy) {
    return (
      <Result
        status="404"
        title={t('Strategy not found')}
        extra={
          <RouterButton to={field ? fieldPath : '/fields'}>
            {field ? t('Back to field') : t('Back to fields')}
          </RouterButton>
        }
      />
    );
  }

  return (
    <>
      <PageHeading
        title={strategy.crop}
        eyebrow={t('Crop strategies for next season')}
        titlePrefix={
          <RouterButton
            type="text"
            icon={<ArrowLeft size={20} />}
            aria-label={t('Back to field')}
            to={fieldPath}
          />
        }
      />
      <Card>
        <Typography.Paragraph>{strategy.description}</Typography.Paragraph>
        <Typography.Text type="secondary">
          {t('More strategy details are coming soon.')}
        </Typography.Text>
      </Card>
    </>
  );
}
