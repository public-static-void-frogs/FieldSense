import { useSuspenseQuery } from '@tanstack/react-query';
import { Button, Select, Tooltip } from 'antd';
import 'leaflet/dist/leaflet.css';
import { Layers, LocateFixed, MapPin, Minus, Plus } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { MapContainer, Polygon, ScaleControl, TileLayer } from 'react-leaflet';
import { farmQueries } from '../../../api/farm/farm.queries.ts';
import type { Field } from '../../../types/fields/field.types.ts';
import type { FieldGeoJson } from '../../../types/maps/map.types.ts';
import type { MapLayer } from '../utils/mapStyles.ts';

import { satelliteTiles } from '../constants/maps.constants.ts';
import { useFieldMap } from '../hooks/useFieldMap.ts';
import { useMapViewport } from '../hooks/useMapViewport.ts';
import { useParcelLayer } from '../hooks/useParcelLayer.ts';
import { mapLegends } from '../utils/mapStyles.ts';
import { defaultCenter } from '../utils/mapViewport.ts';
import './FieldMap.css';

type FieldMapProps = {
  fields: Field[];
  /** WGS84 GeoJSON points; properties.fieldId (or feature.id) links to fields. */
  geojson: FieldGeoJson;
  onSelect: (field: Field) => void;
  adding: boolean;
  onAdd: (id: number) => void;
  expanded?: boolean;
  /** Plain satellite view with field points, without metric layers or legend. */
  locationOnly?: boolean;
  hideControls?: boolean;
};

export function FieldMap({
  fields,
  geojson,
  onSelect,
  adding,
  onAdd,
  expanded = false,
  locationOnly = false,
  hideControls = false,
}: FieldMapProps) {
  const { t } = useTranslation();
  const { map, setLayer, layer, recenter } = useFieldMap(geojson, fields, locationOnly);

  const { data: preferences } = useSuspenseQuery(farmQueries.profile());
  const legend = mapLegends[layer].map((item) => ({ ...item, label: t(item.label) }));

  return (
    <div className={`field-map ${expanded ? 'expanded' : ''}`}>
      <MapContainer
        ref={map}
        className="map-canvas"
        center={defaultCenter}
        zoom={14}
        zoomSnap={0.25}
        minZoom={2}
        maxZoom={19}
        zoomControl={false}
        scrollWheelZoom
      >
        <TileLayer
          url={satelliteTiles.url}
          attribution={satelliteTiles.attribution}
          maxNativeZoom={19}
          maxZoom={19}
        />
        <MapViewport data={geojson} fields={fields} />
        {fields.map(
          (field) =>
            field.boundary && (
              <Polygon
                key={field.id}
                positions={field.boundary.coordinates.map((part) =>
                  part.map((ring) => ring.map(([lon, lat]) => [lat, lon] as [number, number])),
                )}
                pathOptions={{ color: '#9fca7a', fillOpacity: 0.2, weight: 2 }}
                eventHandlers={{ click: () => onSelect(field) }}
              />
            ),
        )}
        <ParcelLayer
          fields={fields}
          geojson={geojson}
          layer={layer}
          onSelect={onSelect}
          onAdd={onAdd}
          adding={adding}
        />
        {!hideControls && <ScaleControl position="bottomright" imperial={false} />}
      </MapContainer>
      {!hideControls && (
        <div className="map-location">
          <MapPin size={13} />
          {preferences.farmName || t('My farm')}
          <span>·</span>
          {preferences.locationLabel}
        </div>
      )}
      {!locationOnly && (
        <div className="map-layer">
          <Select
            aria-label={t('Map layer')}
            value={layer}
            onChange={setLayer}
            prefix={<Layers size={14} />}
            options={['Crop health', 'Soil moisture', 'Field locations'].map((value) => ({
              value,
              label: t(value),
            }))}
          />
        </div>
      )}
      {!hideControls && (
        <div className="map-controls">
          <Tooltip title={t('Zoom in')}>
            <Button type="text" aria-label={t('Zoom in')} onClick={() => map.current?.zoomIn()}>
              <Plus size={17} />
            </Button>
          </Tooltip>
          <Tooltip title={t('Zoom out')}>
            <Button type="text" aria-label={t('Zoom out')} onClick={() => map.current?.zoomOut()}>
              <Minus size={17} />
            </Button>
          </Tooltip>
          <Tooltip title={t('Recenter map')}>
            <Button type="text" aria-label={t('Recenter map')} onClick={recenter}>
              <LocateFixed size={17} />
            </Button>
          </Tooltip>
        </div>
      )}
      {locationOnly && fields.some((field) => field.locationKind === 'interior_point') && (
        <div className="map-location-note">{t('Field location point')}</div>
      )}
      {!locationOnly && (
        <div className="map-legend">
          {legend.map((item) => (
            <span key={item.label}>
              <i style={{ background: item.color }} />
              {item.label}
            </span>
          ))}
        </div>
      )}
      {adding && (
        <div className="add-map-prompt">
          <Plus size={15} />
          {t('Select a field point to add it to your farm')}
        </div>
      )}
    </div>
  );
}

type MapViewportProps = { data: FieldGeoJson; fields: Field[] };

function MapViewport({ data, fields }: MapViewportProps) {
  useMapViewport(data, fields);
  return null;
}

type ParcelLayerProps = FieldMapProps & { layer: MapLayer };

function ParcelLayer({ fields, geojson, layer, onSelect, onAdd, adding }: ParcelLayerProps) {
  useParcelLayer({ fields, geojson, layer, onSelect, onAdd, adding });
  return null;
}
