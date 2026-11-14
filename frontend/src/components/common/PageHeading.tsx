import { Flex, Typography } from 'antd';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

const { Title, Paragraph, Text } = Typography;

type PageHeadingProps = {
  title: string;
  description?: string;
  titlePrefix?: ReactNode;
  eyebrow?: string;
  actions?: ReactNode;
};

export function PageHeading({
  title,
  titlePrefix,
  description,
  eyebrow,
  actions,
}: PageHeadingProps) {
  const { t } = useTranslation();
  const headingEyebrow = eyebrow ?? t('YOUR FARM, AT A GLANCE');

  return (
    <Flex className="page-heading" justify="space-between" align="center" gap={20} wrap>
      <div>
        {headingEyebrow && <Text className="eyebrow">{headingEyebrow}</Text>}
        {titlePrefix ? (
          <Flex align="center" gap={12}>
            {titlePrefix}
            <Title level={1}>{title}</Title>
          </Flex>
        ) : (
          <Title level={1}>{title}</Title>
        )}
        {description && <Paragraph type="secondary">{description}</Paragraph>}
      </div>
      {actions && (
        <Flex gap={10} wrap>
          {actions}
        </Flex>
      )}
    </Flex>
  );
}
