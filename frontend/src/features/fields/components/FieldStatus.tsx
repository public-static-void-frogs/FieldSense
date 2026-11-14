import { Tag } from 'antd';
import { useTranslation } from 'react-i18next';
import type { Field } from '../../../types/fields/field.types.ts';

import { fieldStatusPresentation } from '../utils/fieldPresentation.ts';

type FieldStatusProps = { status: Field['status'] };

export function FieldStatus({ status }: FieldStatusProps) {
  const { t } = useTranslation();
  if (!status) {
    return <Tag>{t('Not measured')}</Tag>;
  }
  const { icon: Icon, color } = fieldStatusPresentation[status];

  return (
    <Tag color={color} icon={<Icon size={15} />}>
      {t(status)}
    </Tag>
  );
}
