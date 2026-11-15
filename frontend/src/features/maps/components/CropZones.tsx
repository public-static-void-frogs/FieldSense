import type { MultiPolygon, Polygon as GeoJsonPolygon } from 'geojson';
import type { SVG } from 'leaflet';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { Marker, Polygon } from 'react-leaflet';
import { CropIcon } from '../../../components/common/CropIcon';
import { useCropIconClick } from '../hooks/useCropIconClick.ts';
import { useMapSvgRenderer } from '../hooks/useMapSvgRenderer.ts';
import { useSectionMarker } from '../hooks/useSectionMarker.ts';
import { detectedCropColors } from '../constants/maps.constants.ts';
import type { MapSection } from '../utils/sectionSelection.ts';

type CropZonesProps = {
  section: MapSection;
  onToggle: (sectionId: string, zoneId: string) => void;
};

export function CropZones({ section, onToggle }: CropZonesProps) {
  const renderer = useMapSvgRenderer();
  const { t } = useTranslation();
  const excluded = new Set(section.excludedZones ?? []);

  return (section.cropZones ?? []).map((zone, index) => {
    const selected = !excluded.has(zone.id);
    const label = selected
      ? 'Deselect {{crop}} area {{number}}'
      : 'Select {{crop}} area {{number}}';

    return (
      <CropArea
        key={zone.id}
        crop={zone.crop}
        areaHa={zone.areaHa}
        center={zone.center}
        boundary={zone.geometry}
        renderer={renderer}
        label={t(label, { crop: zone.crop, number: index + 1 })}
        selected={selected}
        onToggle={() => onToggle(section.id, zone.id)}
      />
    );
  });
}

type CropAreaProps = {
  renderer: SVG;
  crop: string;
  areaHa: number;
  center: number[];
  boundary?: GeoJsonPolygon | MultiPolygon | null;
  label?: string;
  selected: boolean;
  onToggle?: () => void;
};

export function CropArea({
  renderer,
  crop,
  areaHa,
  center,
  boundary,
  label,
  selected,
  onToggle,
}: CropAreaProps) {
  const { t, i18n } = useTranslation();
  const { element, icon } = useSectionMarker('crop');
  const clickHandlers = useCropIconClick(onToggle);
  const polygons = boundary?.type === 'Polygon' ? [boundary.coordinates] : boundary?.coordinates;
  const cropColor = detectedCropColors[crop] ?? '#80b377';
  const iconClass = `map-crop-icon ${selected ? 'is-selected' : ''}`;
  const area = new Intl.NumberFormat(i18n.language, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 3,
  }).format(areaHa);
  const details = `${crop} · ${area} ${t('ha')}`;

  return (
    <>
      {polygons && (
        <Polygon
          positions={polygons.map((part) =>
            part.map((ring) =>
              ring.map(([longitude, latitude]) => [latitude, longitude] as [number, number]),
            ),
          )}
          pathOptions={{
            renderer,
            interactive: Boolean(onToggle),
            color: selected ? cropColor : '#8c9682',
            weight: selected ? 2 : 1,
            fillColor: cropColor,
            fillOpacity: selected ? 0.18 : 0.025,
            dashArray: selected ? undefined : '5 5',
            className: 'map-detected-boundary map-section-interactive',
          }}
          eventHandlers={onToggle ? { click: onToggle } : undefined}
        />
      )}
      <Marker position={[center[1], center[0]]} icon={icon} keyboard={false} interactive={false} />
      {createPortal(
        onToggle ? (
          <button
            type="button"
            className={iconClass}
            aria-label={label}
            aria-description={details}
            title={details}
            aria-pressed={selected}
            {...clickHandlers}
          >
            <CropIcon crop={crop} />
          </button>
        ) : (
          <span
            className={`${iconClass} map-crop-icon-saved`}
            role="img"
            aria-label={details}
            title={details}
          >
            <CropIcon crop={crop} />
          </span>
        ),
        element,
      )}
    </>
  );
}
