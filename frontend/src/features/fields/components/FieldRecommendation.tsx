import { useSuspenseQuery } from '@tanstack/react-query';
import { Card, Space, Tag, Typography } from 'antd';
import { Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { fieldQueries } from '../../../api/fields/fields.queries.ts';
import type { Field } from '../../../types/fields/field.types.ts';

type FieldRecommendationProps = { field: Field };

export function FieldRecommendation({ field }: FieldRecommendationProps) {
  const { t } = useTranslation();
  const {
    data: { recommendation, isSample },
  } = useSuspenseQuery(fieldQueries.recommendation(field.id));

  return (
    <Card
      className="insight-card ai-insight-card"
      title={
        <Space>
          <Sparkles size={22} className="ai-insight-sparkle" aria-hidden="true" />
          {t('Your field, explained')}{' '}
        </Space>
      }
      extra={
        <Tag className="ai-insight-tag">{isSample ? t('Sample suggestion') : t('AI INSIGHT')}</Tag>
      }
    >
      <Typography.Title level={3}>{recommendation.title}</Typography.Title>
      <Typography.Paragraph>{recommendation.description}</Typography.Paragraph>
    </Card>
  );
}
