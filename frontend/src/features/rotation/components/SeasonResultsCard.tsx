import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Card, Flex, Input, Typography } from 'antd';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { rotationMutations } from '../../../api/rotation/rotation.mutations.ts';
import { rotationQueries } from '../../../api/rotation/rotation.queries.ts';
import type { RotationAdvice } from '../../../types/rotation/rotation.types.ts';
import { catalogCropLabels, seasonRowErrorLabels } from '../constants/rotationLabels.ts';
import { cropNamer, pricedPlan } from '../utils/planPresentation.ts';
import { formatNumber, formatPercent } from '../utils/rotationPresentation.ts';
import {
  formatSeasonResults,
  parseSeasonResults,
  SEASON_ROWS_MAX,
  validSeasonResults,
} from '../utils/seasonResultsText.ts';

type SeasonResultsCardProps = { advice: RotationAdvice };

/** The farmer pastes what the field grew and yielded; it replaces the satellite history. */
export function SeasonResultsCard({ advice }: SeasonResultsCardProps) {
  const { t, i18n } = useTranslation();
  const client = useQueryClient();
  const { fieldId } = advice;
  const { data, isPending } = useQuery(rotationQueries.seasonResults(fieldId));
  const save = useMutation(rotationMutations.saveSeasonResults(client, fieldId));
  // null: the box shows what is stored; a string: the farmer is editing.
  const [draft, setDraft] = useState<string | null>(null);
  const name = cropNamer(advice);
  const label = (crop: string) => t(catalogCropLabels[crop] ?? name(crop));
  const crops = Object.entries(catalogCropLabels).map(([id, english]) => ({
    id,
    names: [english, t(english), name(id), t(name(id))],
  }));
  const stored = formatSeasonResults(data?.results ?? [], label);
  const text = draft ?? stored;
  const rows = parseSeasonResults(text, crops);
  const results = validSeasonResults(rows);
  const errors = rows.filter(({ error }) => error);
  const tooMany = results.length > SEASON_ROWS_MAX;
  const changed = draft !== null && draft.trim() !== stored.trim();
  const ownYields = pricedPlan(advice)?.ownYields ?? [];

  const submit = (next: typeof results) =>
    save.mutate({ fieldId, results: next }, { onSuccess: () => setDraft(null) });

  return (
    <Card
      className="rotation-input-card"
      title={<h3>{t('Your past seasons')}</h3>}
      loading={isPending}
    >
      <Typography.Paragraph type="secondary">
        {t(
          'Paste one season per line: year, crop, yield per acre (bushels; hay in tons). Rows copied from a spreadsheet work. Your crops replace the satellite estimate for those years, and your yields set this field’s level against the county.',
        )}
      </Typography.Paragraph>
      <Input.TextArea
        aria-label={t('Your past seasons')}
        className="rotation-results-box"
        autoSize={{ minRows: 5, maxRows: 14 }}
        placeholder={`2025, ${label('soybeans')}, 62\n2024, ${label('corn')}, 221`}
        value={text}
        onChange={(event) => setDraft(event.target.value)}
      />
      <Flex gap={12} align="center" wrap className="rotation-input-actions">
        <Button
          type="primary"
          loading={save.isPending}
          disabled={!changed || errors.length > 0 || tooMany}
          onClick={() => submit(results)}
        >
          {t('Save and recalculate')}
        </Button>
        {(data?.results.length ?? 0) > 0 && (
          <Button disabled={save.isPending} onClick={() => submit([])}>
            {t('Clear')}
          </Button>
        )}
        <Typography.Text type="secondary" aria-live="polite">
          {t('{{seasons}} seasons read', { seasons: results.length })}
        </Typography.Text>
      </Flex>
      {errors.length > 0 && (
        <ul className="rotation-results-errors">
          {errors.map((row) => (
            <li key={row.line}>
              <Typography.Text type="danger">
                {t('Line {{line}}: {{problem}}', {
                  line: row.line,
                  problem: t(seasonRowErrorLabels[row.error ?? 'crop']),
                })}
              </Typography.Text>{' '}
              <Typography.Text type="secondary">{row.text}</Typography.Text>
            </li>
          ))}
        </ul>
      )}
      {tooMany && <Alert type="warning" showIcon title={t('At most 60 seasons can be saved.')} />}
      {save.error && (
        <Alert
          type="error"
          showIcon
          title={t('The seasons could not be saved')}
          description={save.error.message}
        />
      )}
      {ownYields.length > 0 && (
        <ul className="rotation-own-yields">
          {ownYields.map((level) => (
            <li key={level.crop}>
              <Typography.Text strong>{label(level.crop)}</Typography.Text>
              {': '}
              <Typography.Text>
                {t(
                  'your yields are {{share}} of the county level over {{seasons}} seasons; the plan expects {{value}} {{unit}}',
                  {
                    share: formatPercent(level.ratio, i18n.language),
                    seasons: level.points.length,
                    value: formatNumber(level.expectedYieldPerAcre, i18n.language),
                    unit: level.yieldUnit,
                  },
                )}
              </Typography.Text>
            </li>
          ))}
          <li>
            <Typography.Text type="secondary">
              {t(
                'With fewer than four seasons of a crop, the missing seasons count as the county level.',
              )}
            </Typography.Text>
          </li>
        </ul>
      )}
    </Card>
  );
}
