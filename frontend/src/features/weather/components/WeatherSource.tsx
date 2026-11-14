import './weather.css';
import { Tooltip } from 'antd';
import { Clock3, Info } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { WeatherMetadata } from '../../../types/weather/weather.types.ts';

type WeatherSourceProps = { data: WeatherMetadata };

export function WeatherSource({ data }: WeatherSourceProps) {
  const { t, i18n } = useTranslation();
  const updated = new Intl.DateTimeFormat(i18n.resolvedLanguage, {
    hour: '2-digit',
    minute: '2-digit',
    timeZone: data.timeZone,
  }).format(new Date(data.fetchedAt));

  return (
    <div className="weather-source">
      <a href="https://open-meteo.com/" target="_blank" rel="noreferrer">
        Open-Meteo
      </a>
      <span className="weather-source-updated">
        <Clock3 size={12} />
        {t('Updated {{time}}', { time: updated })}
      </span>
      <Tooltip
        title={
          <div>
            <p>{t('Weather model estimates; local conditions may differ.')}</p>
            <p>
              {t('Soil moisture: daily mean volumetric water content at {{depth}}.', {
                depth: data.soilDepth,
              })}
            </p>
            <p>
              {t(
                'Forecasts are model predictions, not observations. Gaps mean data is unavailable; accuracy decreases further into the future.',
              )}
            </p>
            <span>{data.timeZone}</span>
          </div>
        }
      >
        <button
          type="button"
          className="weather-source-info"
          aria-label={t('About these readings')}
        >
          <Info size={14} />
          {t('Model estimates')}
        </button>
      </Tooltip>
    </div>
  );
}
