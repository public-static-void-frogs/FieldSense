import { useSuspenseQuery } from '@tanstack/react-query';
import { Button, Card, Result, Space, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { useLoaderData } from 'react-router-dom';
import { fieldQueries } from '../api/fields/fields.queries.ts';
import type { FieldRouteData } from '../app/route-loaders.ts';
import { RouterButton } from '../components/common/RouterButton';
import { useCatalogSelection } from '../features/maps/hooks/useCatalogSelection.ts';

export function AddFieldPage() {
  const { t } = useTranslation();
  const { fieldId } = useLoaderData<FieldRouteData>();
  const { data: field } = useSuspenseQuery(fieldQueries.catalogById(fieldId));
  const { data: fields } = useSuspenseQuery(fieldQueries.list());
  const selection = useCatalogSelection();
  const selected = fields.some((item) => item.id === fieldId);
  if (!field) {
    return (
      <Result
        status="404"
        title={t('Field not found')}
        extra={<RouterButton to="/map">{t('Back to the map')}</RouterButton>}
      />
    );
  }

  return (
    <Card title={field.name} className="form-card">
      <Typography.Paragraph>
        {t('{{value0}} ha', { value0: field.area.toFixed(2) })}
      </Typography.Paragraph>
      <Typography.Paragraph>
        {t(
          'Each point represents a field location from the supplied source. Crop and soil measurements have not been inferred.',
        )}
      </Typography.Paragraph>
      <Space wrap>
        <Button
          type="primary"
          loading={selection.isPending}
          onClick={() => selection.toggle(fieldId, selected)}
        >
          {selected ? t('Remove from my fields') : t('Add to my fields')}
        </Button>
        <RouterButton to="/map">{t('Back to the map')}</RouterButton>
      </Space>
    </Card>
  );
}
