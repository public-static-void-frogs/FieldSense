import { Card, Flex, Space, Tag, Typography } from 'antd';
import { ArrowUpRight, CalendarDays, Sprout } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { RouterButton } from '../../../components/common/RouterButton';
import type { Field } from '../../../types/fields/field.types.ts';
import type { RotationPlan } from '../../../types/planning/planning.types.ts';

import { formatPlanDate } from '../../planning/utils/planningDates.ts';

type CropRotationPlanProps = { field: Field; plan: RotationPlan };

export function CropRotationPlan({ field, plan }: CropRotationPlanProps) {
  const { t } = useTranslation();

  return (
    <Card className="rotation-summary rotation-plan-anchor">
      <Flex justify="space-between" align="center" gap={20} wrap>
        <div className="rotation-summary-copy">
          <Space size={8}>
            <Sprout size={19} />
            <Typography.Text strong>{t('Rotation recommendation')}</Typography.Text>
            <Tag>{t('Model draft')}</Tag>
          </Space>
          <Typography.Title level={4}>{`${field.crop} → ${plan.nextCrop}`}</Typography.Title>
          <Typography.Paragraph type="secondary" className="no-margin">
            {t(
              'Review the field strategy, preparation steps, forecasts, and proposed calendar events.',
            )}
          </Typography.Paragraph>
        </div>
        <Flex gap={16} align="center" wrap className="rotation-summary-actions">
          <div className="rotation-summary-date">
            <Typography.Text type="secondary">{t('Planting window')}</Typography.Text>
            <Space size={6}>
              <CalendarDays size={16} />
              <Typography.Text strong>{formatPlanDate(plan.sowingDate)}</Typography.Text>
            </Space>
            <Typography.Text type="secondary">
              {t('through {{value0}}', { value0: formatPlanDate(plan.windowEnd) })}
            </Typography.Text>
          </div>
          <RouterButton
            type="primary"
            to={`/fields/${field.id}/strategy`}
            icon={<ArrowUpRight size={17} />}
          >
            {t('View strategy')}
          </RouterButton>
        </Flex>
      </Flex>
    </Card>
  );
}
