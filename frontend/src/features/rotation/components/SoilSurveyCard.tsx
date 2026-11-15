import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Card, Flex, Form, Input, InputNumber, Select, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { rotationMutations } from '../../../api/rotation/rotation.mutations.ts';
import { rotationQueries } from '../../../api/rotation/rotation.queries.ts';
import type { RotationAdvice, RotationSoilSurvey } from '../../../types/rotation/rotation.types.ts';
import {
  phosphorusTestLabels,
  potassiumSampleLabels,
  soilInputLabels,
  soilTestCategoryLabels,
  soilTestNutrientLabels,
} from '../constants/rotationLabels.ts';
import { cropNamer } from '../utils/planPresentation.ts';
import { formatNumber, formatUsd } from '../utils/rotationPresentation.ts';

type SoilSurveyCardProps = { advice: RotationAdvice };

const formatSigned = (value: number, language: string) =>
  `${value > 0 ? '+' : ''}${formatUsd(value, language)}`;

const measurements = [
  { id: 'ph', min: 3, max: 10, step: 0.1 },
  { id: 'organicMatterPct', min: 0, max: 30, step: 0.1 },
  { id: 'phosphorusPpm', min: 0, max: 1000, step: 1 },
  { id: 'potassiumPpm', min: 0, max: 5000, step: 1 },
] as const;

const methods = [
  { id: 'phosphorusTest', label: 'Phosphorus test', options: phosphorusTestLabels },
  { id: 'potassiumSample', label: 'Potassium sample', options: potassiumSampleLabels },
] as const;

/** The farmer's soil test. pH and organic matter replace the soil map estimate. */
export function SoilSurveyCard({ advice }: SoilSurveyCardProps) {
  const { t, i18n } = useTranslation();
  const client = useQueryClient();
  const { fieldId } = advice;
  const { data: stored, isPending } = useQuery(rotationQueries.soilSurvey(fieldId));
  const save = useMutation(rotationMutations.saveSoilSurvey(client, fieldId));
  const remove = useMutation(rotationMutations.removeSoilSurvey(client, fieldId));
  const error = save.error ?? remove.error;
  const name = cropNamer(advice);
  const effects = advice.plan?.soilTest ?? [];
  const soilYield = advice.plan?.soilYield ?? [];

  const submit = (values: RotationSoilSurvey) => {
    const survey = Object.fromEntries(
      Object.entries(values).filter(
        ([, value]) => value !== null && value !== undefined && value !== '',
      ),
    ) as RotationSoilSurvey;
    save.mutate({ fieldId, survey });
  };

  return (
    <Card
      className="rotation-input-card"
      title={<h3>{t('Your soil test')}</h3>}
      loading={isPending}
    >
      <Typography.Paragraph type="secondary">
        {t(
          'pH and organic matter from your test replace the soil map estimate. Phosphorus and potassium change the fertilizer cost of corn and soybeans.',
        )}
      </Typography.Paragraph>
      <Form<RotationSoilSurvey>
        // Remount when the stored test changes so the fields show what is saved.
        key={JSON.stringify(stored ?? null)}
        layout="vertical"
        className="rotation-soil-form"
        initialValues={stored ?? {}}
        onFinish={submit}
      >
        {measurements.map(({ id, min, max, step }) => (
          <Form.Item key={id} name={id} label={t(soilInputLabels[id])}>
            <InputNumber min={min} max={max} step={step} />
          </Form.Item>
        ))}
        {methods.map(({ id, label, options }) => (
          <Form.Item key={id} name={id} label={t(label)}>
            <Select
              allowClear
              placeholder={t(Object.values(options)[0])}
              options={Object.entries(options).map(([value, text]) => ({ value, label: t(text) }))}
            />
          </Form.Item>
        ))}
        <Form.Item name="sampledOn" label={t('Sampled on')}>
          <Input type="date" />
        </Form.Item>
        <Form.Item noStyle shouldUpdate className="rotation-soil-actions">
          {({ getFieldsValue }) => {
            const values = getFieldsValue() as RotationSoilSurvey;
            const measured = measurements.some(({ id }) => typeof values[id] === 'number');

            return (
              <Flex gap={12} wrap className="rotation-input-actions rotation-soil-actions">
                <Button
                  type="primary"
                  htmlType="submit"
                  loading={save.isPending}
                  disabled={!measured}
                >
                  {t('Save and recalculate')}
                </Button>
                {stored && (
                  <Button loading={remove.isPending} onClick={() => remove.mutate(fieldId)}>
                    {t('Remove my test')}
                  </Button>
                )}
              </Flex>
            );
          }}
        </Form.Item>
      </Form>
      {error && (
        <Alert
          type="error"
          showIcon
          title={t('The soil test could not be saved')}
          description={error.message}
        />
      )}
      {(advice.soilInputs?.length ?? 0) > 0 && (
        <ul className="rotation-soil-used">
          {advice.soilInputs?.map((input) => (
            <li key={input.id}>
              <Typography.Text>
                {t(soilInputLabels[input.id])}: {formatNumber(input.value, i18n.language, 2)}
              </Typography.Text>{' '}
              <Tag color={input.source === 'survey' ? 'green' : undefined}>
                {input.source === 'survey' ? t('Your test') : t('Soil map estimate')}
              </Tag>
              {input.usedIn.length === 0 && (
                <Typography.Text type="secondary">{t('Not used yet')}</Typography.Text>
              )}
            </li>
          ))}
        </ul>
      )}
      {soilYield.length > 0 && (
        <ul className="rotation-soil-used">
          {soilYield.map((level) => (
            <li key={level.crop}>
              <Typography.Text type="secondary">
                {t(
                  '{{crop}}: soil productivity index {{field}} against {{county}} for the county, expected yield {{share}} of the county level',
                  {
                    crop: name(level.crop),
                    field: formatNumber(level.fieldIndex, i18n.language, 2),
                    county: formatNumber(level.countyIndex, i18n.language, 2),
                    share: new Intl.NumberFormat(i18n.language, {
                      style: 'percent',
                      maximumFractionDigits: 0,
                    }).format(level.ratio),
                  },
                )}
              </Typography.Text>
            </li>
          ))}
        </ul>
      )}
      {effects.length > 0 && (
        <ul className="rotation-soil-used">
          {effects.map((effect) => (
            <li key={effect.nutrient}>
              <Typography.Text>{t(soilTestNutrientLabels[effect.nutrient])}</Typography.Text>{' '}
              <Tag>{t(soilTestCategoryLabels[effect.category])}</Tag>
              <Typography.Text type="secondary">
                {effect.crops
                  .map((crop) =>
                    t('{{crop}}: fertilizer cost {{change}} per acre', {
                      crop: name(crop.crop),
                      change: formatSigned(crop.costChangeUsdPerAcre, i18n.language),
                    }),
                  )
                  .join('; ')}
              </Typography.Text>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
