import { Card, Switch, Tag, Typography } from 'antd';
import { useId } from 'react';
import { useTranslation } from 'react-i18next';
import type { RotationPlan, RotationPlanner } from '../../../types/rotation/rotation.types.ts';
import './RecommendationSettings.css';

const unavailableReasons: Record<string, string> = {
  no_policy_file: 'The server has no trained RL model loaded.',
  torch_not_installed: 'The server is missing the software needed to run the RL model.',
  policy_does_not_fit: 'The installed RL model is incompatible with this planner.',
};

type RecommendationSettingsProps = {
  planner: RotationPlanner;
  plannerStatus: RotationPlan['planner'];
  onPlannerChange: (planner: RotationPlanner) => void;
};

export function RecommendationSettings({
  planner,
  plannerStatus,
  onPlannerChange,
}: RecommendationSettingsProps) {
  const { t } = useTranslation();
  const labelId = useId();
  const descriptionId = useId();
  const useLearned = planner === 'learned';
  const learnedAvailable = plannerStatus?.learnedAvailable === true;
  const unavailableReason = unavailableReasons[plannerStatus?.learnedUnavailable ?? ''];

  return (
    <Card title={t('Custom settings')}>
      <div className="rotation-planner-setting">
        <div>
          <div id={labelId} className="rotation-planner-setting-label">
            <Typography.Text strong>{t('Use RL planner')}</Typography.Text>
            <Tag color="gold">{t('Experimental')}</Tag>
          </div>
          <div id={descriptionId}>
            <Typography.Paragraph type="secondary">
              {t(
                'For each starting crop, a reinforcement learning model chooses what to grow in later seasons using this field’s yield estimates, prices, costs, and rotation rules. Its plan may score lower than the exact planner’s best result. Turn the switch off to use the exact planner.',
              )}
            </Typography.Paragraph>
            {!learnedAvailable && (
              <Typography.Paragraph type="secondary">
                {t(unavailableReason ?? 'The RL planner is unavailable for this recommendation.')}
              </Typography.Paragraph>
            )}
          </div>
        </div>
        <Switch
          aria-labelledby={labelId}
          aria-describedby={descriptionId}
          checked={useLearned}
          disabled={!learnedAvailable && !useLearned}
          onChange={(checked) => onPlannerChange(checked ? 'learned' : 'exact')}
        />
      </div>
    </Card>
  );
}
