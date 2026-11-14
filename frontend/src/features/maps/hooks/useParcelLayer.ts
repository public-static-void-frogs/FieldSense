import { circleMarker, geoJSON, Path } from 'leaflet';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useMap } from 'react-leaflet';
import type { Field } from '../../../types/fields/field.types.ts';
import type { FieldGeoJson } from '../../../types/maps/map.types.ts';
import { getFeatureFieldId, getFeatureParcelId } from '../utils/mapGeometry.ts';
import type { MapLayer } from '../utils/mapStyles.ts';
import { getParcelLabel, parcelStyle } from '../utils/mapStyles.ts';

type UseParcelLayerOptions = {
  fields: Field[];
  geojson: FieldGeoJson;
  layer: MapLayer;
  onSelect: (field: Field) => void;
  onAdd: (id: number) => void;
  adding: boolean;
};

export function useParcelLayer({
  fields,
  geojson,
  layer,
  onSelect,
  onAdd,
  adding,
}: UseParcelLayerOptions) {
  const { t } = useTranslation();
  const map = useMap();
  useEffect(() => {
    const parcels = geoJSON(geojson, {
      pointToLayer: (feature, latlng) =>
        circleMarker(latlng, {
          ...parcelStyle(
            fields.find((field) => field.id === getFeatureFieldId(feature)),
            layer,
          ),
          radius: 8,
        }),
      onEachFeature: (feature, point) => {
        const fieldId = getFeatureFieldId(feature);
        const id = getFeatureParcelId(feature);
        const field = fields.find((item) => item.id === fieldId);
        const label = getParcelLabel(field, id, feature.properties?.name, t);
        const activate = () => {
          if (field) {
            onSelect(field);
          } else if (id) {
            onAdd(id);
          }
        };
        if (field || id) {
          point.on('click', activate);
        }
        if (point instanceof Path) {
          const style = parcelStyle(field, layer);
          point.on({
            mouseover: () =>
              point.setStyle({
                weight: 4,
                fillOpacity: 1,
              }),
            mouseout: () => point.setStyle(style),
            add: () => {
              const element = point.getElement();
              if (!element) {
                return;
              }
              element.setAttribute('role', field || id ? 'button' : 'img');
              if (field || id) {
                element.setAttribute('tabindex', '0');
              }
              element.setAttribute('aria-label', label);
              element.addEventListener('keydown', (event) => {
                if (
                  event instanceof KeyboardEvent &&
                  (event.key === 'Enter' || event.key === ' ')
                ) {
                  event.preventDefault();
                  event.stopPropagation();
                  activate();
                }
              });
            },
          });
        }
        if (field || adding || feature.properties?.name) {
          // DOM text avoids interpreting GeoJSON properties and user field names as HTML.
          const content = document.createElement('div');
          const title = document.createElement('strong');
          title.textContent = field?.name || feature.properties?.name || t('+ Add field');
          content.append(title);
          if (field) {
            const detail = document.createElement('span');
            detail.textContent = t('{{value0}} ha · {{value1}}', {
              value0: field.area.toFixed(2),
              value1: field.crop || t('Crop not supplied'),
            });
            content.append(detail);
          }
          point.bindTooltip(content, {
            permanent: true,
            direction: 'top',
            className: 'field-map-label',
            opacity: 1,
          });
        }
      },
    }).addTo(map);
    return () => {
      parcels.remove();
    };
  }, [map, geojson, fields, layer, onSelect, onAdd, adding, t]);
}
