import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Card, Empty, Skeleton, Tabs, Tag, Tooltip } from 'antd';
import { TriangleAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { fieldInsightsQueries } from '../../../api/fields/field-insights.queries.ts';
import type {
  M2Crop,
  M2FieldEffect,
  M2Insights,
  M2NeighbourEffect,
  M2Outcome,
  M2Region,
  M2Treatment,
} from '../../../types/fields/field-insights.types.ts';
import { CropIcon } from '../../../components/common/CropIcon';
import type { Field } from '../../../types/fields/field.types.ts';
import {
  m2Crops,
  m2Outcomes,
  m2Tiers,
  m2Treatments,
  m2Verdicts,
} from '../constants/m2Insights.constants.ts';
import { insightNumber, insightSigned } from '../utils/fieldInsightFormats.ts';
import { m2Range } from '../utils/m2Range.ts';
import { InsightHelpLabel } from './InsightHelpLabel';
import './FieldInsights.css';

type FieldM2InsightsProps = { field: Field };

export function FieldM2Insights({ field }: FieldM2InsightsProps) {
  const { t, i18n } = useTranslation();
  const query = useQuery(
    fieldInsightsQueries.m2(field.id, JSON.stringify(field.geometry.coordinates)),
  );
  const insights = query.data;
  let content = <Skeleton active paragraph={{ rows: 2 }} />;
  if (query.isError) {
    content = (
      <Alert
        type="error"
        title={t('Could not load neighbour evidence.')}
        action={<Button onClick={() => void query.refetch()}>{t('Retry')}</Button>}
      />
    );
  } else if (insights?.ok) {
    content = <M2Results insights={insights} />;
  } else if (insights) {
    content = (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={t('This field is outside the neighbour evidence coverage.')}
      />
    );
  }

  const match = insights?.ok ? insights.match : null;
  let help;
  if (match?.level === 'field') {
    help = t('Uses the analysed field {{distance}} km away', {
      distance: insightNumber(match.distance_km, i18n.language),
    });
  } else if (match?.level === 'neighbourhood') {
    help = t('Summarises {{fields}} analysed fields within {{radius}} km', {
      fields: insightNumber(match.n_neighbour_fields, i18n.language),
      radius: insightNumber(match.radius_km ?? 30, i18n.language),
    });
  } else if (match) {
    help = t('Study-wide result: no analysed fields close enough to this one');
  }

  return (
    <Card
      title={
        <InsightHelpLabel label={t('Neighbour evidence on rotation and drought')} help={help} />
      }
    >
      {content}
    </Card>
  );
}

type M2ResultsProps = { insights: M2Insights };

function M2Results({ insights }: M2ResultsProps) {
  const { t } = useTranslation();
  const region = insights.region ?? {};
  const cropKeys = (Object.keys(m2Crops) as M2Crop[]).filter((crop) => region[crop]);

  return (
    <div className="field-insights-panel">
      {cropKeys.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('No evidence to show.')} />
      ) : (
        <Tabs
          items={cropKeys.map((crop) => ({
            key: crop,
            label: (
              <span className="field-insights-crop-tab">
                <CropIcon crop={m2Crops[crop]} />
                {t(m2Crops[crop])}
              </span>
            ),
            children: <M2CropPanel crop={crop} insights={insights} />,
          }))}
        />
      )}
      <p className="field-insights-muted">
        {t(
          'Compares fields in drought years that were managed differently under the same weather. This is an adjusted association from satellite data, not a guaranteed effect.',
        )}
      </p>
      {insights.warnings.length > 0 && (
        <details>
          <summary>{t('Evidence notes')}</summary>
          <ul className="field-insights-notes">
            {insights.warnings.map((warning) => (
              <li key={warning}>
                <EvidenceNote text={t(warning, { defaultValue: warning })} />
              </li>
            ))}
          </ul>
        </details>
      )}
      <small>{t('Neighbour Evidence Engine (CropTwin Detective + CausalSoil)')}</small>
    </div>
  );
}

type EvidenceNoteProps = { text: string };

/** Shows the part before the first colon, and the colon, in bold italics. */
function EvidenceNote({ text }: EvidenceNoteProps) {
  const split = text.indexOf(': ');
  if (split < 0) {
    return text;
  }

  return (
    <>
      <strong>
        <em>{text.slice(0, split + 1)}</em>
      </strong>
      {text.slice(split + 1)}
    </>
  );
}

type M2CropPanelProps = { crop: M2Crop; insights: M2Insights };

function M2CropPanel({ crop, insights }: M2CropPanelProps) {
  const { t, i18n } = useTranslation();
  const signed = (value: number | null | undefined) => insightSigned(value, i18n.language);
  const treatments = insights.region?.[crop] ?? {};
  const rows = (Object.keys(m2Treatments) as M2Treatment[]).flatMap((treatment) => {
    const region = treatments[treatment];
    if (!region) {
      return [];
    }

    const headline = region.abstain ? null : region.headline;
    const outcome = headline?.outcome;

    return [
      {
        treatment,
        region,
        headline,
        outcomeName: outcome ? t(m2Outcomes[outcome as keyof typeof m2Outcomes] ?? outcome) : null,
        fieldEffect: outcome ? insights.field?.[crop]?.[treatment]?.[outcome] : undefined,
        hoodEffect: outcome ? insights.neighbourhood?.[crop]?.[treatment]?.[outcome] : undefined,
      },
    ];
  });

  return (
    <div className="field-m2-treatments">
      {rows.map(({ treatment, region, headline, outcomeName, fieldEffect, hoodEffect }) => (
        <section className="field-m2-treatment" key={treatment}>
          <h4>
            <span>{t(m2Treatments[treatment])}</span>
            {headline?.outcome_sees_drought === false && <M2DroughtWarning />}
            <M2Verdict region={region} />
          </h4>
          <M2Range headline={headline} signed={signed} />
          <div className="field-m2-description">
            {headline && <M2OutcomeDescription headline={headline} outcomeName={outcomeName} />}
            {region.evidence_tier === 'limited' && headline && (
              <p className="field-insights-muted">{t('Small sample: read as indicative.')}</p>
            )}
            {fieldEffect && <M2FieldLine effect={fieldEffect} signed={signed} />}
            {hoodEffect && <M2NeighbourLine effect={hoodEffect} signed={signed} />}
          </div>
        </section>
      ))}
    </div>
  );
}

function M2DroughtWarning() {
  const { t } = useTranslation();
  const warning = t('This measure does not respond to drought in the data.');

  return (
    <Tooltip title={warning} trigger={['hover', 'focus', 'click']}>
      <button
        type="button"
        className="field-insights-help-button field-m2-warning"
        aria-label={warning}
      >
        <TriangleAlert size={16} aria-hidden="true" />
      </button>
    </Tooltip>
  );
}

function M2OutcomeDescription({
  headline,
  outcomeName,
}: {
  headline: M2Outcome;
  outcomeName: string | null;
}) {
  const { t } = useTranslation();
  const basis = headline.headline_basis ?? 'effect';
  const drought = headline.gamma != null;
  const outcome = drought
    ? t('extra effect in drought on {{outcome}}', { outcome: outcomeName })
    : t('{{basis}} on {{outcome}}', {
        basis: t(basis, { defaultValue: basis }),
        outcome: outcomeName,
      });

  return (
    <>
      <p className="field-insights-muted">{outcome}</p>
      {!drought && (
        <p className="field-insights-muted">
          {t('Not a drought-specific effect: the data do not separate drought seasons.')}
        </p>
      )}
    </>
  );
}

function M2Verdict({ region }: { region: M2Region }) {
  const { t } = useTranslation();
  const tier = region.evidence_tier;
  const verdictKey = region.verdict.replace('small sample: ', '');
  const lowerTier = tier != null && tier !== 'full' && tier !== 'limited';
  const verdict = lowerTier
    ? { label: m2Tiers[tier], tone: 'default' as const }
    : (m2Verdicts[verdictKey] ?? { label: verdictKey, tone: 'default' as const });

  return (
    <Tag className="field-m2-verdict" color={verdict.tone === 'default' ? undefined : verdict.tone}>
      {t(verdict.label)}
    </Tag>
  );
}

type M2RangeProps = {
  headline: M2Outcome | null;
  signed: (value: number | null | undefined) => string;
};

function M2Range({ headline, signed }: M2RangeProps) {
  const { t } = useTranslation();
  const range = headline && m2Range(headline);
  if (!headline || !range) {
    return (
      <p className="field-insights-muted">{t('Not enough comparable fields for an estimate.')}</p>
    );
  }

  const { estimate, interval, normalGap, limit, position } = range;
  const normalGapLabel = t('Gap in normal seasons: {{value}}', { value: signed(normalGap) });
  const normalPosition = position(normalGap ?? 0);

  return (
    <>
      <div className="field-insights-season-dates">
        <span>{signed(estimate)}</span>
        {interval && (
          <small>
            [{signed(interval.low)}, {signed(interval.high)}]
          </small>
        )}
      </div>
      <div className="field-insights-season-chart">
        <div className="field-insights-season-track">
          {interval && (
            <span
              className="field-insights-season-range"
              style={{
                left: `${position(interval.low)}%`,
                width: `${position(interval.high) - position(interval.low)}%`,
              }}
            />
          )}
          {limit > 0 && <span className="field-m2-zero-marker" />}
          <span
            className="field-insights-season-marker"
            style={{ left: `${position(estimate)}%` }}
          />
          {normalGap != null && (
            <>
              <span
                className="field-m2-normal-gap"
                style={{
                  left: `${Math.min(50, normalPosition)}%`,
                  width: `${Math.abs(normalPosition - 50)}%`,
                }}
              />
              <Tooltip title={normalGapLabel} trigger={['hover', 'focus', 'click']}>
                <button
                  type="button"
                  className="field-m2-normal-marker"
                  style={{ left: `${normalPosition}%` }}
                  aria-label={normalGapLabel}
                />
              </Tooltip>
            </>
          )}
        </div>
        {limit > 0 && (
          <div className="field-insights-season-axis field-m2-axis" aria-hidden="true">
            <span>{signed(-limit)}</span>
            <span>{signed(0)}</span>
            <span>{signed(limit)}</span>
          </div>
        )}
      </div>
    </>
  );
}

type LineProps<T> = { effect: T; signed: (value: number | null | undefined) => string };

function M2FieldLine({ effect, signed }: LineProps<M2FieldEffect>) {
  const { t } = useTranslation();
  if (!effect.usable) {
    return <p className="field-insights-muted">{t('This field: not enough comparable fields.')}</p>;
  }

  const indicative = effect.status !== 'ok';

  return (
    <p className="field-insights-muted">
      {t(
        indicative
          ? 'This field in drought (indicative): {{value}} [{{low}}, {{high}}]'
          : 'This field in drought: {{value}} [{{low}}, {{high}}]',
        {
          value: signed(effect.effect),
          low: signed(effect.lo95),
          high: signed(effect.hi95),
        },
      )}
    </p>
  );
}

function M2NeighbourLine({ effect, signed }: LineProps<M2NeighbourEffect>) {
  const { t, i18n } = useTranslation();
  if (effect.median == null) {
    return null;
  }

  return (
    <p className="field-insights-muted">
      {t('Fields within {{radius}} km in drought: median {{value}} ({{fields}} fields)', {
        radius: insightNumber(effect.radius_km, i18n.language),
        value: signed(effect.median),
        fields: insightNumber(effect.n_usable, i18n.language),
      })}
      {effect.note ? ` ${t('indicative')}` : ''}
    </p>
  );
}
