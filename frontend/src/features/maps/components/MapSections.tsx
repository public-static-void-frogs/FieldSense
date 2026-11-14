import { Button } from 'antd';
import { Plus } from 'lucide-react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { Marker, Polygon } from 'react-leaflet';
import { CropZones } from './CropZones.tsx';
import { useMapSvgRenderer } from '../hooks/useMapSvgRenderer.ts';
import { useSectionMarker } from '../hooks/useSectionMarker.ts';
import { sectionCenter, type MapSection } from '../utils/sectionSelection.ts';

type MapSectionsProps = {
  sections: MapSection[];
  activeId?: string;
  onActivate: (id: string) => void;
  onToggleCropZone: (sectionId: string, zoneId: string) => void;
};

export function MapSections({
  sections,
  activeId,
  onActivate,
  onToggleCropZone,
}: MapSectionsProps) {
  return sections.map((section) =>
    section.analysisStatus === 'complete' ? (
      <CropZones key={section.id} section={section} onToggle={onToggleCropZone} />
    ) : (
      <SectionRegion
        key={section.id}
        section={section}
        active={section.id === activeId}
        onActivate={onActivate}
      />
    ),
  );
}

type SectionRegionProps = {
  section: MapSection;
  active: boolean;
  onActivate: (id: string) => void;
};

function SectionRegion({ section, active, onActivate }: SectionRegionProps) {
  const renderer = useMapSvgRenderer();

  return (
    <>
      <Polygon
        key={section.analysisStatus ?? 'draft'}
        positions={section.outline}
        pathOptions={{
          renderer,
          color: active ? '#bde79a' : '#a3d17c',
          weight: 2,
          dashArray: '6 4',
          fillColor: '#91b968',
          fillOpacity: 0.18,
          interactive: section.added,
          className:
            section.analysisStatus === 'pending'
              ? 'map-lasso-outline map-section-analyzing'
              : 'map-lasso-outline',
        }}
        eventHandlers={{
          click: () => {
            if (section.added) {
              onActivate(section.id);
            }
          },
        }}
      />
      {!section.added && <SectionAddMarker section={section} onActivate={onActivate} />}
    </>
  );
}

type SectionAddMarkerProps = { section: MapSection; onActivate: (id: string) => void };

function SectionAddMarker({ section, onActivate }: SectionAddMarkerProps) {
  const { t } = useTranslation();
  const { element, icon } = useSectionMarker();

  return (
    <>
      <Marker position={sectionCenter(section.outline)} icon={icon} keyboard={false} />
      {createPortal(
        <Button
          type="primary"
          icon={<Plus size={15} />}
          aria-label={t('Add section')}
          onClick={() => onActivate(section.id)}
        >
          {t('Add')}
        </Button>,
        element,
      )}
    </>
  );
}
