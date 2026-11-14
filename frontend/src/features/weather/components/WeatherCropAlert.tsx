import { useTranslation } from 'react-i18next';
import type { CropRiskAlert, WeatherUnits } from '../../../types/weather/weather.types.ts';
import { formatCropAlert, formatCropAlertDrivers } from '../utils/cropRiskPresentation.ts';

type WeatherCropAlertProps = { alert: CropRiskAlert; units: WeatherUnits };

export function WeatherCropAlert({ alert, units }: WeatherCropAlertProps) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage;
  const drivers = formatCropAlertDrivers(alert, t, language);

  return (
    <li data-risk={alert.severity}>
      <span aria-hidden="true">⚠️</span> {formatCropAlert(alert, units, t, language)}
      {drivers && <small className="weather-crop-alert-drivers">{drivers}</small>}
    </li>
  );
}
