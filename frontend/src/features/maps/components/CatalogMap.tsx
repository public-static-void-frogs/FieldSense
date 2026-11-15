import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Spin, Tooltip } from 'antd';
import { CircleHelp } from 'lucide-react';
import { useCallback } from 'react';
import 'leaflet/dist/leaflet.css';
import { useTranslation } from 'react-i18next';
import { useLocation, useSearchParams } from 'react-router-dom';
import { MapContainer, ScaleControl, TileLayer } from 'react-leaflet';
import { fieldQueries } from '../../../api/fields/fields.queries.ts';
import type { Field } from '../../../types/fields/field.types.ts';
import { mapQueries } from '../../../api/maps/maps.queries.ts';
import { RouterButton } from '../../../components/common/RouterButton';
import { satelliteTiles } from '../constants/maps.constants.ts';
import { useCatalogLayers } from '../hooks/useCatalogLayers.ts';
import { useMapSections } from '../hooks/useMapSections.ts';
import { useMapSelectionTool } from '../hooks/useMapSelectionTool.ts';
import { useCatalogViewport } from '../hooks/useCatalogViewport.ts';
import { useMapPosition } from '../hooks/useMapPosition.ts';
import { parseMapPosition } from '../utils/catalogViewport.ts';
import { MapSelectionControls } from './MapSelectionControls.tsx';
import { MapSections } from './MapSections.tsx';
import { SavedFieldAreas } from './SavedFieldAreas.tsx';
import { SectionPanel } from './SectionPanel.tsx';
import './FieldMap.css';
import './CatalogMap.css';

export function CatalogMap() {
  const { t } = useTranslation();
  const summary = useQuery(mapQueries.summary());
  const fields = useQuery(fieldQueries.list());
  const { pathname, search } = useLocation();
  const [parameters] = useSearchParams();
  const savedView = parseMapPosition(parameters);
  if (!summary.data || (!savedView && fields.isPending)) {
    return (
      <div className="catalog-map-start" role="status">
        {summary.isError ? (
          <Alert
            type="error"
            title={t('Unable to load the field map')}
            action={<Button onClick={() => summary.refetch()}>{t('Try again')}</Button>}
          />
        ) : (
          <Spin description={t('Loading field coverage…')} />
        )}
      </div>
    );
  }

  return (
    <div className="fullscreen-map">
      <section className="field-map expanded catalog-map" aria-label={t('Field map')}>
        <div className="map-guide-control">
          <Tooltip title={t('Field Map guide')}>
            <RouterButton
              type="text"
              icon={<CircleHelp size={17} aria-hidden />}
              aria-label={t('Field Map guide')}
              to="/map/guide"
              state={{ mapPath: pathname, mapSearch: search }}
            />
          </Tooltip>
        </div>
        <MapContainer
          className="map-canvas"
          center={savedView?.center ?? summary.data.defaultCenter}
          zoom={savedView?.zoom ?? summary.data.defaultZoom}
          zoomControl={false}
          minZoom={2}
          maxZoom={19}
          preferCanvas
          maxBounds={[
            [-85, -180],
            [85, 180],
          ]}
          maxBoundsViscosity={1}
        >
          <TileLayer
            url={satelliteTiles.url}
            attribution={satelliteTiles.attribution}
            maxNativeZoom={19}
            maxZoom={19}
            noWrap
            crossOrigin="anonymous"
          />
          <CatalogViewport fields={fields.data} fitSavedFieldsOnOpen={!savedView} />
          <ScaleControl position="bottomright" imperial={false} />
        </MapContainer>
      </section>
    </div>
  );
}

type CatalogViewportProps = {
  fields?: Field[];
  fitSavedFieldsOnOpen: boolean;
};

function CatalogViewport({ fields, fitSavedFieldsOnOpen }: CatalogViewportProps) {
  const query = useCatalogViewport();
  const selection = useMapSections();
  const canSelect = query.data?.mode === 'fields' && !query.isPlaceholderData && !query.isFetching;
  const { activeTool, setTool } = useMapSelectionTool({
    features: query.data?.features ?? [],
    available: canSelect,
    onComplete: selection.draw,
    onToggle: selection.toggle,
  });
  const { activate } = selection;
  const activateSection = useCallback(
    (id: string) => {
      setTool('move');
      activate(id);
    },
    [setTool, activate],
  );
  useMapPosition();
  const { t } = useTranslation();
  useCatalogLayers(query.data, selection.selectedIds, selection.sections, fields);

  return (
    <>
      <MapSelectionControls
        count={selection.selectedIds.size}
        activeTool={activeTool}
        canSelect={canSelect}
        onSelectTool={setTool}
      />
      {fields?.length ? <SavedFieldAreas fields={fields} fitOnOpen={fitSavedFieldsOnOpen} /> : null}
      <MapSections
        sections={selection.sections}
        activeId={selection.activeSection?.id}
        onActivate={activateSection}
        onToggleCropZone={selection.toggleCropZone}
      />
      {selection.activeSection && (
        <SectionPanel
          key={selection.activeSection.id}
          section={selection.activeSection}
          onCancel={selection.cancel}
          onSelectCrop={selection.setCropSelection}
          analysisActions={{
            begin: selection.beginAnalysis,
            complete: selection.completeAnalysis,
            fail: selection.failAnalysis,
            abort: selection.abortAnalysis,
          }}
        />
      )}
      {query.isError && (
        <div className="catalog-map-alert">
          <Alert
            type="error"
            title={t('Unable to load this area')}
            description={t('Move the map or try again.')}
            action={<Button onClick={() => query.refetch()}>{t('Try again')}</Button>}
          />
        </div>
      )}
    </>
  );
}
