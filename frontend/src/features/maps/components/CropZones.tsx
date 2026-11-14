import type { SVG } from 'leaflet';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { Marker, Polygon } from 'react-leaflet';
import type { CropZone } from '../../../types/maps/map.types.ts';
import { useCropIconClick } from '../hooks/useCropIconClick.ts';
import { useMapSvgRenderer } from '../hooks/useMapSvgRenderer.ts';
import { useSectionMarker } from '../hooks/useSectionMarker.ts';
import { detectedCropIcons, detectedCropColors } from '../constants/maps.constants.ts';
import type { MapSection } from '../utils/sectionSelection.ts';

type CropZonesProps = {
  section: MapSection;
  onToggle: (sectionId: string, zoneId: string) => void;
};

export function CropZones({ section, onToggle }: CropZonesProps) {
  const renderer = useMapSvgRenderer();
  const excluded = new Set(section.excludedZones ?? []);

  return (section.cropZones ?? []).map((zone, index) => (
    <CropZoneMarker
      key={zone.id}
      zone={zone}
      renderer={renderer}
      number={index + 1}
      selected={!excluded.has(zone.id)}
      onToggle={() => onToggle(section.id, zone.id)}
    />
  ));
}

type CropZoneMarkerProps = {
  renderer: SVG;
  zone: CropZone;
  number: number;
  selected: boolean;
  onToggle: () => void;
};

function CropZoneMarker({ renderer, zone, number, selected, onToggle }: CropZoneMarkerProps) {
  const { t } = useTranslation();
  const { element, icon } = useSectionMarker('crop');
  const clickHandlers = useCropIconClick(onToggle);
  const label = selected
    ? t('Deselect {{crop}} area {{number}}', { crop: zone.crop, number })
    : t('Select {{crop}} area {{number}}', { crop: zone.crop, number });

  return (
    <>
      <Polygon
        positions={zone.geometry.coordinates.map((ring) =>
          ring.map(([longitude, latitude]) => [latitude, longitude] as [number, number]),
        )}
        pathOptions={{
          renderer,
          color: selected ? (detectedCropColors[zone.crop] ?? '#80b377') : '#8c9682',
          weight: selected ? 2 : 1,
          fillColor: detectedCropColors[zone.crop] ?? '#80b377',
          fillOpacity: selected ? 0.18 : 0.025,
          dashArray: selected ? undefined : '5 5',
          className: 'map-detected-boundary map-section-interactive',
        }}
        eventHandlers={{ click: onToggle }}
      />
      <Marker
        position={[zone.center[1], zone.center[0]]}
        icon={icon}
        keyboard={false}
        interactive={false}
      />
      {createPortal(
        <button
          type="button"
          className={`map-crop-icon ${selected ? 'is-selected' : ''}`}
          aria-label={label}
          title={label}
          aria-pressed={selected}
          {...clickHandlers}
        >
          <span aria-hidden="true">{detectedCropIcons[zone.crop] ?? '🌱'}</span>
        </button>,
        element,
      )}
    </>
  );
}
