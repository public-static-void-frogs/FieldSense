import { Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import type { RotationSoilIndicator } from '../../../types/rotation/rotation.types.ts';
import { soilIndicatorLabels } from '../constants/rotationLabels.ts';
import { formatValue } from '../utils/rotationPresentation.ts';

const soilDirections = [
  { value: 'worse', label: 'Less favorable' },
  { value: 'neutral', label: 'Neutral' },
  { value: 'better', label: 'More favorable' },
] as const;

type SoilEffectsProps = { indicators: RotationSoilIndicator[] };

export function SoilEffects({ indicators }: SoilEffectsProps) {
  const { t, i18n } = useTranslation();

  return (
    <section>
      <Typography.Title level={5}>{t('Effect on the soil')}</Typography.Title>
      <details className="strategy-disclosure">
        <summary>{t('About this score')}</summary>
        <p className="rotation-soil-note">
          {t('The scale shows how each indicator compares with its own reference point.')}
        </p>
      </details>
      <dl className="rotation-soil-rows">
        {indicators.map(({ id, value, direction, threshold, verified }) => {
          const rating =
            value == null ? undefined : soilDirections.find((item) => item.value === direction);
          const display =
            value === 'fixer' ? t('Fixes its own nitrogen') : formatValue(value, t, i18n.language);

          return (
            <div key={id} className="rotation-soil-row">
              <dt>{t(soilIndicatorLabels[id] ?? id)}</dt>
              <dd>
                <strong>{display}</strong>
                {verified === false && <small>{t('Needs verification')}</small>}
              </dd>
              <dd className="rotation-soil-rating">
                <span className="rotation-soil-scale" aria-hidden="true">
                  {soilDirections.map((item) => (
                    <span
                      key={item.value}
                      data-direction={item.value}
                      data-active={item === rating}
                    />
                  ))}
                </span>
                <span>{rating ? t(rating.label) : t('Direction unknown')}</span>
                {rating && threshold != null && (
                  <small className="rotation-soil-reference">
                    {t('Reference value {{value}}', {
                      value: formatValue(threshold, t, i18n.language),
                    })}
                  </small>
                )}
              </dd>
            </div>
          );
        })}
      </dl>
    </section>
  );
}
