import { Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import type { RotationDataGap } from '../../../types/rotation/rotation.types.ts';
import { gapLabels } from '../constants/rotationLabels.ts';
import { distinctGapCodes } from '../utils/rotationPresentation.ts';

type InformationGapsProps = { title: string; gaps: RotationDataGap[] };

export function InformationGaps({ title, gaps }: InformationGapsProps) {
  const { t } = useTranslation();
  const codes = distinctGapCodes(gaps);
  if (codes.length === 0) {
    return null;
  }

  return (
    <section className="rotation-gaps">
      <Typography.Title level={5}>{title}</Typography.Title>
      <ul>
        {codes.map((code) => (
          <li key={code}>
            <Typography.Text type="secondary">{t(gapLabels[code] ?? code)}</Typography.Text>
          </li>
        ))}
      </ul>
    </section>
  );
}
