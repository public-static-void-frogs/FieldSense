import { Alert } from 'antd';
import { useTranslation } from 'react-i18next';
import type { RotationAdvice } from '../../../types/rotation/rotation.types.ts';
import { rankedCandidates, sortedFindings } from '../utils/rotationPresentation.ts';

type AdviceVerdictProps = { advice: RotationAdvice };

export function AdviceVerdict({ advice }: AdviceVerdictProps) {
  const { t } = useTranslation();
  const candidates = rankedCandidates(advice);
  const intended = candidates.find((candidate) => candidate.isIntended);
  const top = candidates[0];
  if (!intended || !top) {
    return null;
  }
  const mainRisk = sortedFindings(intended.risks)[0];
  const crop = t(intended.label);
  const title =
    intended.rank === 1
      ? t('{{crop}} carries the least rotation risk here', { crop })
      : t('{{crop}} ranks {{rank}} of {{total}} for rotation risk', {
          crop,
          rank: intended.rank,
          total: candidates.length,
        });
  const details = [
    mainRisk
      ? t('Largest risk: {{risk}}.', { risk: t(mainRisk.title) })
      : t('No rotation risks were found with the information available.'),
    intended.rank === 1
      ? ''
      : t('{{crop}} carries the least risk on this field.', { crop: t(top.label) }),
  ];
  let type: 'success' | 'info' | 'warning' = 'info';
  if (intended.rank === 1) {
    type = 'success';
  } else if (intended.risks.some((risk) => risk.level === 'high')) {
    type = 'warning';
  }

  return (
    <Alert
      className="rotation-verdict"
      type={type}
      showIcon
      title={title}
      description={details.filter(Boolean).join(' ')}
    />
  );
}
