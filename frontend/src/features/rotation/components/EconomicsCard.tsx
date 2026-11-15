import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Card, Flex, Form, InputNumber, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { rotationMutations } from '../../../api/rotation/rotation.mutations.ts';
import { rotationQueries } from '../../../api/rotation/rotation.queries.ts';
import type {
  RotationAdvice,
  RotationEconomics,
  RotationEconomicsInputs,
} from '../../../types/rotation/rotation.types.ts';
import { rentLevelLabels } from '../constants/rotationLabels.ts';
import { cropNamer } from '../utils/planPresentation.ts';
import { formatUsd } from '../utils/rotationPresentation.ts';

type EconomicsCardProps = { advice: RotationAdvice };

type EconomicsForm = {
  rent?: number | null;
  price?: Record<string, number | null | undefined>;
  cost?: Record<string, number | null | undefined>;
};

const isNumber = (value: unknown): value is number => typeof value === 'number';

function toForm(inputs: RotationEconomicsInputs | null): EconomicsForm {
  const crops = inputs?.crops ?? [];

  return {
    rent: inputs?.landRentUsdPerAcre,
    price: Object.fromEntries(crops.map(({ crop, priceUsd }) => [crop, priceUsd])),
    cost: Object.fromEntries(crops.map(({ crop, costUsdPerAcre }) => [crop, costUsdPerAcre])),
  };
}

function toInputs(values: EconomicsForm, economics: RotationEconomics): RotationEconomicsInputs {
  const crops = economics.defaults.crops
    .map(({ crop }) => ({
      crop,
      priceUsd: values.price?.[crop],
      costUsdPerAcre: values.cost?.[crop],
    }))
    .filter(({ priceUsd, costUsdPerAcre }) => isNumber(priceUsd) || isNumber(costUsdPerAcre))
    .map(({ crop, priceUsd, costUsdPerAcre }) => ({
      crop,
      ...(isNumber(priceUsd) && { priceUsd }),
      ...(isNumber(costUsdPerAcre) && { costUsdPerAcre }),
    }));

  return { ...(isNumber(values.rent) && { landRentUsdPerAcre: values.rent }), crops };
}

/** The farmer's own price, cost and rent. Empty fields keep the USDA average shown in them. */
export function EconomicsCard({ advice }: EconomicsCardProps) {
  const { t, i18n } = useTranslation();
  const client = useQueryClient();
  const { fieldId } = advice;
  const { data: economics, isPending } = useQuery(rotationQueries.economics(fieldId));
  const save = useMutation(rotationMutations.saveEconomics(client, fieldId));
  const remove = useMutation(rotationMutations.removeEconomics(client, fieldId));
  const error = save.error ?? remove.error;
  const name = cropNamer(advice);
  const rent = economics?.defaults.landRent;

  return (
    <Card
      className="rotation-input-card"
      title={<h3>{t('Your prices and costs')}</h3>}
      loading={isPending}
    >
      <Typography.Paragraph type="secondary">
        {t(
          'Price, cost and rent decide most of the dollar result. Each field shows the USDA average; type your own number to replace it.',
        )}
      </Typography.Paragraph>
      {economics && (
        <Form<EconomicsForm>
          // Remount when the stored numbers change so the fields show what is saved.
          key={JSON.stringify(economics.inputs)}
          layout="vertical"
          initialValues={toForm(economics.inputs)}
          onFinish={(values) => save.mutate({ fieldId, inputs: toInputs(values, economics) })}
        >
          <div className="rotation-economics-grid">
            <div className="rotation-economics-row rotation-economics-heading" aria-hidden="true">
              <Typography.Text strong>{t('Crop')}</Typography.Text>
              <Typography.Text strong>{t('Price')}</Typography.Text>
              <Typography.Text strong>{t('Cost per acre, without land')}</Typography.Text>
            </div>
            {economics.defaults.crops.map((crop) => (
              <div className="rotation-economics-row" key={crop.crop}>
                <Typography.Text strong className="rotation-economics-crop">
                  {t(name(crop.crop))}
                </Typography.Text>
                <Form.Item name={['price', crop.crop]}>
                  <InputNumber
                    min={0.01}
                    max={1000}
                    step={0.1}
                    prefix="$"
                    suffix={`/ ${crop.priceUnit}`}
                    placeholder={crop.priceUsd.toFixed(2)}
                    aria-label={`${t(name(crop.crop))}: ${t('Price')}`}
                  />
                </Form.Item>
                <Form.Item name={['cost', crop.crop]}>
                  <InputNumber
                    min={0}
                    max={5000}
                    step={5}
                    prefix="$"
                    placeholder={crop.costUsdPerAcre.toFixed(0)}
                    aria-label={`${t(name(crop.crop))}: ${t('Cost per acre, without land')}`}
                  />
                </Form.Item>
              </div>
            ))}
          </div>
          <Form.Item
            name="rent"
            label={t('Land rent per acre')}
            className="rotation-economics-rent"
            extra={
              rent
                ? t('USDA {{level}}, {{year}}: {{value}}. Without a rent, land is not charged.', {
                    level: t(rentLevelLabels[rent.level]),
                    year: rent.year,
                    value: formatUsd(rent.usdPerAcre, i18n.language),
                  })
                : t('Without a rent, land is not charged.')
            }
          >
            <InputNumber
              min={0}
              max={2000}
              step={5}
              prefix="$"
              placeholder={rent ? rent.usdPerAcre.toFixed(0) : undefined}
            />
          </Form.Item>
          <Flex gap={12} wrap className="rotation-input-actions">
            <Button type="primary" htmlType="submit" loading={save.isPending}>
              {t('Save and recalculate')}
            </Button>
            {economics.inputs && (
              <Button loading={remove.isPending} onClick={() => remove.mutate(fieldId)}>
                {t('Back to USDA averages')}
              </Button>
            )}
          </Flex>
        </Form>
      )}
      {error && (
        <Alert
          type="error"
          showIcon
          title={t('The prices and costs could not be saved')}
          description={error.message}
        />
      )}
    </Card>
  );
}
