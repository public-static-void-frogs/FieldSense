import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Card, Empty, Skeleton, Tabs, Tag } from 'antd';
import { useTranslation } from 'react-i18next';
import { fieldInsightsQueries } from '../../../api/fields/field-insights.queries.ts';
import type {
  M2Crop,
  M2FieldEffect,
  M2Insights,
  M2NeighbourEffect,
  M2Region,
  M2Treatment,
} from '../../../types/fields/field-insights.types.ts';
import { CropIcon } from '../../../components/common/CropIcon';
import type { Field } from '../../../types/fields/field.types.ts';
import {
  m2Crops,
  m2Outcomes,
  m2Treatments,
  m2Verdicts,
} from '../constants/m2Insights.constants.ts';
import { insightNumber, insightSigned } from '../utils/fieldInsightFormats.ts';
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
    help = t('Summarises {{fields}} analysed fields within 30 km', {
      fields: insightNumber(match.n_neighbour_fields, i18n.language),
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
      <p className="field-insights-muted">
        {t(
          'Compares fields in drought years that were managed differently under the same weather. This is an adjusted association from satellite data, not a guaranteed effect.',
        )}
      </p>
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
      {insights.warnings.length > 0 && (
        <details>
          <summary>{t('Evidence notes')}</summary>
          <ul className="field-insights-notes">
            {insights.warnings.map((warning) => (
              <li key={warning}>{t(warning, { defaultValue: warning })}</li>
            ))}
          </ul>
        </details>
      )}
      <small>{t('Neighbour Evidence Engine (CropTwin Detective + CausalSoil)')}</small>
    </div>
  );
}

type M2CropPanelProps = { crop: M2Crop; insights: M2Insights };

function M2CropPanel({ crop, insights }: M2CropPanelProps) {
  const treatments = insights.region?.[crop] ?? {};

  return (
    <div className="field-insights-grid">
      {(Object.keys(m2Treatments) as M2Treatment[])
        .filter((treatment) => treatments[treatment])
        .map((treatment) => (
          <M2TreatmentCard
            key={treatment}
            treatment={treatment}
            region={treatments[treatment] as M2Region}
            field={insights.field?.[crop]?.[treatment]}
            neighbourhood={insights.neighbourhood?.[crop]?.[treatment]}
          />
        ))}
    </div>
  );
}

type M2TreatmentCardProps = {
  treatment: M2Treatment;
  region: M2Region;
  field: Record<string, M2FieldEffect> | undefined;
  neighbourhood: Record<string, M2NeighbourEffect> | undefined;
};

function M2TreatmentCard({ treatment, region, field, neighbourhood }: M2TreatmentCardProps) {
  const { t, i18n } = useTranslation();
  const signed = (value: number | null | undefined) => insightSigned(value, i18n.language);
  const verdict = m2Verdicts[region.verdict] ?? { label: region.verdict, tone: 'default' };
  const headline = region.headline;
  const outcomeKey = headline?.outcome;
  const outcomeName = outcomeKey
    ? t(m2Outcomes[outcomeKey as keyof typeof m2Outcomes] ?? outcomeKey)
    : null;
  const fieldEffect = outcomeKey ? field?.[outcomeKey] : undefined;
  const hoodEffect = outcomeKey ? neighbourhood?.[outcomeKey] : undefined;

  return (
    <Card
      size="small"
      className="field-insights-metric"
      title={t(m2Treatments[treatment])}
      extra={
        <Tag color={verdict.tone === 'default' ? undefined : verdict.tone}>{t(verdict.label)}</Tag>
      }
    >
      {region.abstain || !headline ? (
        <p className="field-insights-muted">{t('Not enough comparable fields for an estimate.')}</p>
      ) : (
        <>
          <p>
            <strong>
              {signed(headline.gamma)} [{signed(headline.gamma_lo)}, {signed(headline.gamma_hi)}]
            </strong>{' '}
            <span className="field-insights-muted">
              {t('extra effect in drought on {{outcome}}', { outcome: outcomeName })}
            </span>
          </p>
          <p className="field-insights-muted">
            {t('Gap in normal seasons: {{value}}', { value: signed(headline.theta_normal) })}
          </p>
          {fieldEffect && <M2FieldLine effect={fieldEffect} signed={signed} />}
          {hoodEffect && <M2NeighbourLine effect={hoodEffect} signed={signed} />}
          {headline.outcome_sees_drought === false && (
            <p className="field-insights-muted">
              {t('This measure does not respond to drought in the data.')}
            </p>
          )}
        </>
      )}
    </Card>
  );
}

type LineProps<T> = { effect: T; signed: (value: number | null | undefined) => string };

function M2FieldLine({ effect, signed }: LineProps<M2FieldEffect>) {
  const { t } = useTranslation();
  if (!effect.usable) {
    return <p className="field-insights-muted">{t('This field: not enough comparable fields.')}</p>;
  }


  return (
    <p className="field-insights-muted">
      {t('This field in drought: {{value}} [{{low}}, {{high}}]', {
        value: signed(effect.effect),
        low: signed(effect.lo95),
        high: signed(effect.hi95),
      })}
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
      {t('Fields within 30 km in drought: median {{value}} ({{fields}} fields)', {
        value: signed(effect.median),
        fields: insightNumber(effect.n_usable, i18n.language),
      })}
    </p>
  );
}
