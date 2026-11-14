import { Alert, Button } from 'antd';
import { LocateFixed, MapPin } from 'lucide-react';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { CircleMarker, MapContainer, TileLayer, useMap, useMapEvents } from 'react-leaflet';
import type { LocationPoint } from '../../../types/maps/map.types.ts';
import { satelliteTiles } from '../constants/maps.constants.ts';
import { useLocationPicker } from '../hooks/useLocationPicker.ts';
import { formatLocation, locationPoint } from '../utils/location.ts';
import 'leaflet/dist/leaflet.css';
import './LocationPicker.css';

type LocationPickerProps = {
  value?: LocationPoint;
  autoLocate?: boolean;
  onChange?: (point: LocationPoint) => void;
  id?: string;
  disabled?: boolean;
};

export function LocationPicker({ value, onChange, id, disabled, autoLocate }: LocationPickerProps) {
  const { t } = useTranslation();
  const { map, status, locate, select, selectCenter } = useLocationPicker({
    value,
    onChange,
    autoLocate,
  });
  let notice = '';
  if (status === 'denied') {
    notice = t('Location access was denied. Choose a point on the map.');
  } else if (status === 'unavailable' || status === 'error') {
    notice = t('Your position is unavailable. Choose a point on the map.');
  }

  return (
    <div
      id={id}
      className="location-picker"
      role="group"
      aria-label={t('Choose your location')}
      aria-disabled={disabled}
    >
      <p className="location-picker-hint">
        {t('Click the map to choose a location, or move the map and use its center.')}
      </p>
      {notice && <Alert type="info" title={notice} showIcon />}
      <div className="location-picker-map" inert={disabled}>
        <MapContainer
          ref={map}
          center={[50.4501, 30.5234]}
          zoom={5}
          minZoom={2}
          maxZoom={19}
          scrollWheelZoom={false}
        >
          <TileLayer
            url={satelliteTiles.url}
            attribution={satelliteTiles.attribution}
            maxNativeZoom={19}
            maxZoom={19}
          />
          <MapSelection value={value} onSelect={select} />
          {value && (
            <CircleMarker
              center={[value.latitude, value.longitude]}
              radius={9}
              pathOptions={{ color: '#ffffff', weight: 3, fillColor: '#476b3c', fillOpacity: 1 }}
              interactive={false}
            />
          )}
        </MapContainer>
        <span className="location-picker-crosshair" aria-hidden="true">
          +
        </span>
      </div>
      <div className="location-picker-actions">
        <Button
          icon={<LocateFixed size={16} />}
          loading={status === 'locating'}
          disabled={disabled}
          onClick={locate}
        >
          {t('Use my location')}
        </Button>
        <Button icon={<MapPin size={16} />} disabled={disabled} onClick={selectCenter}>
          {t('Use map center')}
        </Button>
      </div>
      <p className="location-picker-value" aria-live="polite">
        {value
          ? t('Selected coordinates: {{coordinates}}', { coordinates: formatLocation(value) })
          : t('No location selected yet.')}
      </p>
    </div>
  );
}

type MapSelectionProps = { value?: LocationPoint; onSelect: (point: LocationPoint) => void };

function MapSelection({ value, onSelect }: MapSelectionProps) {
  const map = useMap();
  const { t } = useTranslation();
  const latitude = value?.latitude;
  const longitude = value?.longitude;
  useMapEvents({
    click: (event) => onSelect(locationPoint(event.latlng.lat, event.latlng.lng)),
    keydown: (event) => {
      if (event.originalEvent.key === 'Enter') {
        const center = map.getCenter();
        onSelect(locationPoint(center.lat, center.lng));
      }
    },
  });
  useEffect(() => {
    map.getContainer().setAttribute('aria-label', t('Location map'));
  }, [map, t]);
  useEffect(() => {
    if (latitude !== undefined && longitude !== undefined) {
      map.setView([latitude, longitude], Math.max(map.getZoom(), 12), {
        animate: false,
      });
    }
  }, [map, latitude, longitude]);

  return null;
}
