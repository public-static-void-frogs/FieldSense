import { Card, Space, Typography } from 'antd';
import { Sparkles } from 'lucide-react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import type { WeatherRecord, WeatherUnits } from '../../../types/weather/weather.types.ts';
import { useWeatherDaySummary } from '../hooks/useWeatherDaySummary.ts';
import { WeatherCropAlert } from './WeatherCropAlert';
import { getWeatherDayInsight } from '../utils/weatherDayInsight.ts';
import { formatWeatherValue } from '../utils/weatherPresentation.ts';

type WeatherDayInsightProps = {
  record: WeatherRecord;
  units: WeatherUnits;
  locale: string;
  fieldId?: string;
};

export function WeatherDayInsight({ record, units, locale, fieldId }: WeatherDayInsightProps) {
  const { t } = useTranslation();
  const summary = useWeatherDaySummary(record.date, locale, fieldId);
  const criticalAlerts =
    record.cropAssessment?.alerts.filter((alert) => alert.severity === 'high') ?? [];

  return (
    <Card
      className="ai-insight-card weather-day-insight"
      title={
        <Space>
          <Sparkles size={21} className="ai-insight-sparkle" aria-hidden="true" />
          {t('Your day, explained')}
        </Space>
      }
    >
      {criticalAlerts.length > 0 && (
        <div className="weather-history-alerts" data-risk="high">
          <strong>{t('High crop risk')}</strong>
          <ul>
            {criticalAlerts.map((alert) => (
              <WeatherCropAlert
                key={`${alert.metric}-${alert.reading}`}
                alert={alert}
                units={units}
              />
            ))}
          </ul>
        </div>
      )}
      {summary.failed ? (
        <WeatherDayFallback record={record} units={units} />
      ) : (
        <>
          <div aria-busy={summary.loading} aria-live="polite">
            <Typography.Paragraph className="weather-insight-summary">
              {summary.text
                ? formatWeatherSummary(summary.text)
                : t('Preparing your weather outlook…')}
            </Typography.Paragraph>
          </div>
          <Typography.Text className="weather-insight-caption" type="secondary">
            {t('Based on the selected forecast and available crop warnings.')}
          </Typography.Text>
        </>
      )}
    </Card>
  );
}

function formatWeatherSummary(text: string): ReactNode[] {
  // Interpret only the inline formats the prompt requests. React escapes the text.
  const markup = /\*\*([^*\n]+)\*\*|(?<!\*)\*([^*\n]+)\*(?!\*)|<u>([^<>\n]+)<\/u>/g;
  const parts: ReactNode[] = [];
  let offset = 0;

  for (const match of text.matchAll(markup)) {
    const [token, bold, italic, underline] = match;
    const position = match.index;
    parts.push(text.slice(offset, position));
    if (bold !== undefined) {
      parts.push(<strong key={position}>{formatWeatherSummary(bold)}</strong>);
    } else if (italic !== undefined) {
      parts.push(<em key={position}>{formatWeatherSummary(italic)}</em>);
    } else {
      parts.push(<u key={position}>{underline}</u>);
    }
    offset = position + token.length;
  }

  parts.push(text.slice(offset));
  return parts;
}

type WeatherDayFallbackProps = { record: WeatherRecord; units: WeatherUnits };

function WeatherDayFallback({ record, units }: WeatherDayFallbackProps) {
  const { t } = useTranslation();
  const insight = getWeatherDayInsight(record, units);
  const facts: string[] = [];
  if (record.weatherCode !== null) {
    facts.push(t('Conditions: {{conditions}}.', { conditions: t(record.conditions) }));
  }
  if (record.temperature !== null && record.low !== null) {
    facts.push(
      t('A high of {{high}} and a low of {{low}} are forecast.', {
        high: formatWeatherValue(record.temperature, units.temperature),
        low: formatWeatherValue(record.low, units.temperature),
      }),
    );
  } else if (record.temperature !== null) {
    facts.push(
      t('The daytime high is {{value}}.', {
        value: formatWeatherValue(record.temperature, units.temperature),
      }),
    );
  } else if (record.low !== null) {
    facts.push(
      t('The overnight low is {{value}}.', {
        value: formatWeatherValue(record.low, units.temperature),
      }),
    );
  }
  if (record.rainChance !== null && record.rainfall !== null) {
    facts.push(
      t('Rain chance is {{chance}}, with {{amount}} of precipitation expected.', {
        chance: formatWeatherValue(record.rainChance, '%'),
        amount: formatWeatherValue(record.rainfall, units.rainfall),
      }),
    );
  } else if (record.rainChance !== null) {
    facts.push(
      t('Rain chance is {{value}}.', {
        value: formatWeatherValue(record.rainChance, '%'),
      }),
    );
  } else if (record.rainfall !== null) {
    facts.push(
      t('Expected precipitation is {{value}}.', {
        value: formatWeatherValue(record.rainfall, units.rainfall),
      }),
    );
  }
  if (record.wind !== null) {
    facts.push(
      t('Wind is forecast at {{value}}.', {
        value: formatWeatherValue(record.wind, units.wind),
      }),
    );
  }

  return (
    <>
      <Typography.Title level={3}>{t(insight.title)}</Typography.Title>
      {facts.length > 0 && <Typography.Paragraph>{facts.join(' ')}</Typography.Paragraph>}
      <Typography.Paragraph>{t(insight.message)}</Typography.Paragraph>
      <Typography.Text className="weather-insight-caption" type="secondary">
        {t('Based on the selected day’s forecast.')}
      </Typography.Text>
    </>
  );
}
