import { useQuery } from '@tanstack/react-query';
import { CalendarDays, CloudSun } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { planningQueries } from '../../../api/planning/planning.queries.ts';
import { weatherQueries } from '../../../api/weather/weather.queries.ts';
import type { FarmProfile } from '../../../types/farm/farm.types.ts';
import { getCalendarEvents, getEventDecision } from '../../planning/utils/eventResponses.ts';
import { formatPlanDate } from '../../planning/utils/planningDates.ts';
import { calendarEventPath } from '../../planning/utils/planningRoutes.ts';
import { WeatherConditionIcon } from '../../weather/components/WeatherConditionIcon';
import { formatWeatherDate } from '../../weather/utils/weatherPresentation.ts';
import { OverviewPanel } from './OverviewPanel';

export function OverviewWeather({ profile }: { profile: FarmProfile }) {
  const { t, i18n } = useTranslation();
  const query = useQuery(weatherQueries.current(profile));
  const weather = query.data;
  const number = new Intl.NumberFormat(i18n.language, { maximumFractionDigits: 1 });
  const days = weather?.forecast.slice(0, 4) ?? [];
  const forecastHigh = Math.max(1, ...days.map(({ rainfall }) => rainfall ?? 0));
  const hasLocation = profile.latitude != null && profile.longitude != null;
  const forecastStatus = query.isError ? t('Forecast unavailable') : t('Loading forecast…');

  return (
    <OverviewPanel
      title={t('Environment')}
      icon={<CloudSun size={19} />}
      to="/history"
      action={t('Open forecast')}
      className="farm-panel-wide farm-weather-panel"
    >
      {weather && (
        <div className="farm-weather-summary">
          <div className="farm-weather-now">
            <WeatherConditionIcon conditions={weather.conditions} size={58} />
            <div>
              <strong>
                {weather.temperature == null
                  ? '—'
                  : `${number.format(weather.temperature)}${weather.units.temperature}`}
              </strong>
              <span>
                {t(weather.conditions)} · {weather.location}
              </span>
            </div>
          </div>
          {days.length > 0 && (
            <ul className="farm-forecast">
              {days.map((day) => (
                <li key={day.date}>
                  <small>{formatWeatherDate(day.date, i18n.language)}</small>
                  <WeatherConditionIcon
                    conditions={day.conditions}
                    size={28}
                    aria-label={t(day.conditions)}
                  />
                  <strong>
                    {day.temperature == null
                      ? '—'
                      : `${number.format(day.temperature)}${weather.units.temperature}`}
                  </strong>
                  <span className="farm-rain-track" aria-hidden>
                    <span style={{ width: `${((day.rainfall ?? 0) / forecastHigh) * 100}%` }} />
                  </span>
                  <small>
                    {day.rainfall == null
                      ? '—'
                      : `${number.format(day.rainfall)} ${weather.units.rainfall}`}
                  </small>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {!weather && (
        <p className="farm-muted" role="status">
          {hasLocation ? forecastStatus : <Link to="/settings">{t('Set your farm location')}</Link>}
        </p>
      )}
    </OverviewPanel>
  );
}

export function OverviewAgenda() {
  const { t } = useTranslation();
  const events = useQuery(planningQueries.events());
  const responses = useQuery(planningQueries.responses());
  const context = useQuery(planningQueries.context());
  const upcoming =
    context.data && events.data && responses.data
      ? getCalendarEvents(events.data, responses.data)
          .filter((event) => event.date >= context.data!.today)
          .sort((a, b) => a.date.localeCompare(b.date))
      : null;
  const failed = events.isError || responses.isError || context.isError;

  return (
    <OverviewPanel
      title={t('Upcoming actions')}
      icon={<CalendarDays size={19} />}
      to="/calendar"
      action={t('Calendar')}
      className="farm-panel-wide"
    >
      {upcoming && upcoming.length > 0 && (
        <>
          <p className="farm-muted">
            {t('Upcoming actions: {{count}}', { count: upcoming.length })}
          </p>
          <ul className="farm-rows">
            {upcoming.slice(0, 4).map((event) => (
              <li key={event.id}>
                <Link className="farm-row farm-row-link" to={calendarEventPath(event)}>
                  <span className="farm-row-copy">
                    <strong>{event.title}</strong>
                    <small>
                      {event.fieldName} · {formatPlanDate(event.date)}
                    </small>
                  </span>
                  <small className="farm-chip">
                    {getEventDecision(event, responses.data ?? {}) === 'accepted'
                      ? t('Accepted')
                      : t('Proposed')}
                  </small>
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
      {!upcoming?.length && (
        <p className="farm-muted" role="status">
          {failed && t('Planning data unavailable')}
          {!failed && (upcoming ? t('No upcoming actions') : t('Loading actions…'))}
        </p>
      )}
    </OverviewPanel>
  );
}
