import { useSuspenseQuery } from '@tanstack/react-query';
import { Card, Typography } from 'antd';
import { useId } from 'react';
import { useTranslation } from 'react-i18next';
import { fieldQueries } from '../../../api/fields/fields.queries.ts';
import { CropIcon } from '../../../components/common/CropIcon';
import { RouterButton } from '../../../components/common/RouterButton';
import './FieldRecommendation.css';

const strategyDetails = {
  'soil-cover': { label: 'Soil cover' },
  'nitrogen-fixation': { label: 'Nitrogen fixation' },
  'long-term-fertility': { label: 'Long-term fertility' },
} as const;

type FieldRecommendationProps = { fieldId: string };

export function FieldRecommendation({ fieldId }: FieldRecommendationProps) {
  const { t } = useTranslation();
  const { data: strategies } = useSuspenseQuery(fieldQueries.strategyOptions());
  const titleId = useId();

  return (
    <section className="field-strategies" aria-labelledby={titleId}>
      <Typography.Title level={3} id={titleId}>
        {t('Crop strategies for next season')}
      </Typography.Title>
      <div className="field-strategies-grid">
        {strategies.map(({ id, crop, description }) => {
          const { label } = strategyDetails[id];

          return (
            <Card key={id} className="field-strategy-card" data-strategy={id}>
              <div className="field-strategy-banner">
                <span className="field-strategy-icon">
                  <CropIcon crop={crop} size={38} />
                </span>
              </div>
              <div className="field-strategy-content">
                <Typography.Title level={4}>{crop}</Typography.Title>
                <Typography.Text strong className="field-strategy-label">
                  {t(label)}
                </Typography.Text>
                <Typography.Paragraph>{description}</Typography.Paragraph>
                <RouterButton
                  block
                  to={`/fields/${fieldId}/strategy/${id}`}
                  className="field-strategy-link"
                  aria-label={t('Learn more about {{crop}}', { crop })}
                >
                  {t('Learn more')}
                </RouterButton>
              </div>
            </Card>
          );
        })}
      </div>
    </section>
  );
}
