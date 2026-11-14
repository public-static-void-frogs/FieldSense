import { useQuery } from '@tanstack/react-query';
import {
  Alert,
  Button,
  Card,
  ConfigProvider,
  Empty,
  Segmented,
  Select,
  Slider,
  Spin,
  theme,
} from 'antd';
import {
  divIcon,
  type LatLngBoundsExpression,
  type LatLngTuple,
  type LeafletMouseEvent,
} from 'leaflet';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ImageOverlay,
  MapContainer,
  Marker,
  Polygon,
  TileLayer,
  useMap,
  useMapEvents,
} from 'react-leaflet';
import { cropHistoryQueries } from '../../../api/fields/crop-history.queries.ts';
import type {
  CropHistoryLayer,
  CropHistoryPoint,
  CropHistoryYear,
  HistoricalCropClass,
} from '../../../types/fields/crop-history.types.ts';
import type { Field } from '../../../types/fields/field.types.ts';
import { satelliteTiles } from '../../maps/constants/maps.constants.ts';
import { useCropPatterns } from '../hooks/useCropPatterns.ts';
import { cropPatternAt, summarizeCropPattern } from '../utils/cropPatterns.ts';
import { FieldSoilDepletion } from './FieldSoilDepletion';
import './FieldCropHistory.css';

const pinIcon = divIcon({
  className: 'crop-history-pin',
  iconSize: [28, 38],
  iconAnchor: [14, 37],
  html: `<svg width="28" height="38" viewBox="0 0 28 38" aria-hidden="true">
    <path d="M14 37C11 31 1 22 1 14a13 13 0 0 1 26 0c0 8-10 17-13 23Z" fill="#d93025" stroke="#fff" stroke-width="1.5"/>
    <circle cx="14" cy="14" r="4.5" fill="#fff"/>
  </svg>`,
});

type FieldCropHistoryProps = { field: Field };

export function FieldCropHistory({ field }: FieldCropHistoryProps) {
  const { t } = useTranslation();
  const [part, setPart] = useState(0);
  const count = field.boundary?.coordinates.length ?? 0;
  const activePart = Math.min(part, Math.max(0, count - 1));
  const rings = field.boundary?.coordinates[activePart];
  const geometryKey = JSON.stringify(rings ?? field.geometry.coordinates);

  return (
    <Card title={t('Crop history')}>
      {!rings && <p>{t('Around saved point')}</p>}
      <div className="crop-history-layout">
        {count > 1 && (
          <div className="crop-history-parcel">
            <Select
              aria-label={t('Saved parcel')}
              value={activePart}
              onChange={setPart}
              options={Array.from({ length: count }, (_, index) => ({
                value: index,
                label: t('Parcel {{number}}', { number: index + 1 }),
              }))}
            />
          </div>
        )}
        <CropHistoryExplorer
          fieldId={field.id}
          part={activePart}
          rings={rings}
          geometryKey={geometryKey}
        />
      </div>
      <FieldSoilDepletion fieldId={field.id} part={activePart} geometryKey={geometryKey} />
    </Card>
  );
}

type ExplorerProps = {
  fieldId: string;
  part: number;
  geometryKey: string;
  rings?: number[][][];
};

function CropHistoryExplorer({ fieldId, part, geometryKey, rings }: ExplorerProps) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const scope = `${part}:${geometryKey}`;
  const [pin, setPin] = useState<{ scope: string; point: CropHistoryPoint } | null>(null);
  const [mode, setMode] = useState<'patterns' | 'annual'>('patterns');
  const [period, setPeriod] = useState(6);
  const [year, setYear] = useState<number>();
  const [previewIndex, setPreviewIndex] = useState<number | null>(null);
  const point = pin?.scope === scope ? pin.point : null;
  const historical = mode === 'patterns';
  const history = useQuery(
    cropHistoryQueries.point(fieldId, part, geometryKey, historical ? null : point),
  );
  const chronologicalYears = history.data?.years.map(({ year }) => year).reverse() ?? [];
  const latestYear = chronologicalYears.at(-1);
  const selectedYear = year ?? latestYear;
  const patternYears = historical ? chronologicalYears.slice(-period) : [];
  const patterns = useCropPatterns(fieldId, part, geometryKey, patternYears);
  const layer = useQuery(
    cropHistoryQueries.layer(fieldId, part, geometryKey, historical ? undefined : selectedYear),
  );
  const mapLayer = historical ? patterns.data : layer.data;
  const mapQuery = historical ? patterns : layer;
  const loadingMap = mapQuery.isFetching || (latestYear === undefined && history.isFetching);
  const staleMap = !historical && layer.isPlaceholderData;
  const marker = point ?? (history.isPlaceholderData ? undefined : history.data?.coordinates);
  const pattern = patterns.data?.patterns;
  const pointYears =
    pattern && marker
      ? cropPatternAt(pattern, marker)
      : patternYears.map((year) => ({ year, crop: null }));
  const activeClasses = historical ? pattern?.classes : layer.data?.classes;
  const lastIndex = chronologicalYears.length - 1;
  const sliderIndex = previewIndex ?? chronologicalYears.findIndex((year) => year === selectedYear);
  const yearMarks = Object.fromEntries(
    [0, Math.floor(lastIndex / 2), lastIndex].map((index) => [index, chronologicalYears[index]]),
  );

  return (
    <>
      <div className="crop-history-main">
        <div className="crop-history-controls">
          <Segmented
            aria-label={t('Crop map view')}
            value={mode}
            onChange={setMode}
            options={[
              { value: 'patterns', label: t('Historical patterns') },
              { value: 'annual', label: t('Single year') },
            ]}
          />
          {historical && (
            <Select
              aria-label={t('Years of crop history')}
              value={period}
              onChange={setPeriod}
              options={[3, 6, 10].map((value) => ({
                value,
                label: t('Last {{years}} years', { years: value }),
              }))}
            />
          )}
        </div>
        <Spin spinning={loadingMap}>
          {mapLayer ? (
            <div className={staleMap ? 'crop-history-placeholder' : undefined} inert={staleMap}>
              <CropHistoryMap
                layer={mapLayer}
                showLayer={!staleMap && !mapQuery.isError}
                marker={marker}
                rings={rings}
                onPick={(point) => setPin({ scope, point })}
              />
            </div>
          ) : (
            <div className="crop-history-map" />
          )}
        </Spin>
        {!historical && chronologicalYears.length > 0 && (
          <div className="crop-history-years">
            <div className="crop-history-year-label">
              <span>{t('Crop map year')}</span>
              <strong>{chronologicalYears[sliderIndex]}</strong>
            </div>
            <ConfigProvider
              theme={{
                components: {
                  Slider: {
                    dotSize: 12,
                    dotBorderColor: token.colorPrimary,
                    dotActiveBorderColor: token.colorPrimary,
                    trackBg: token.colorPrimary,
                    trackHoverBg: token.colorPrimary,
                    handleColor: token.colorPrimary,
                    handleActiveColor: token.colorPrimary,
                    handleSize: 16,
                  },
                },
              }}
            >
              <Slider
                dots
                ariaLabelForHandle={t('Crop map year')}
                ariaValueTextFormatterForHandle={(index) => String(chronologicalYears[index])}
                min={0}
                max={lastIndex}
                marks={yearMarks}
                value={sliderIndex}
                tooltip={{
                  formatter: (index) => (index === undefined ? null : chronologicalYears[index]),
                }}
                onChange={setPreviewIndex}
                onChangeComplete={(index) => {
                  setYear(chronologicalYears[index]);
                  setPreviewIndex(null);
                }}
              />
            </ConfigProvider>
          </div>
        )}
        {mapQuery.isError && <CropHistoryError retry={() => void mapQuery.refetch()} />}
        {mapLayer?.image && !staleMap && !mapQuery.isError && activeClasses && (
          <>
            <CropMapLegend classes={activeClasses} mixed={historical && !!pattern?.hasMixed} />
            {historical && (
              <p className="crop-history-map-description">
                {t(
                  'Map colors show the class present in more than half of the years with data at each spot.',
                )}
              </p>
            )}
          </>
        )}
        {mapLayer && !mapLayer.image && !staleMap && (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={t(
              historical
                ? 'No mapped crop data for these years.'
                : 'No mapped crop data for this year.',
            )}
          />
        )}
        <p>{t('Tap the map to see the crop history at that spot.')}</p>
        <small>{t('Source')} · USDA Cropland Data Layer</small>
      </div>
      <div className="crop-history-list">
        <h3>{t('History at map pin')}</h3>
        {history.isError && <CropHistoryError retry={() => void history.refetch()} />}
        {historical && (
          <Spin spinning={loadingMap}>
            {patterns.data && <PointCropPatterns years={pointYears} />}
          </Spin>
        )}
        {!historical && (
          <Spin spinning={history.isFetching}>
            {history.data && (
              <ul
                className={history.isPlaceholderData ? 'crop-history-placeholder' : undefined}
                inert={history.isPlaceholderData}
              >
                {history.data.years.map(({ year, crop }) => (
                  <li key={year}>
                    <Button
                      block
                      type={selectedYear === year ? 'primary' : 'text'}
                      aria-pressed={selectedYear === year}
                      onClick={() => {
                        setPreviewIndex(null);
                        setYear(year);
                      }}
                    >
                      <strong>{year}</strong>
                      {crop && (
                        <span className="crop-history-swatch" style={{ background: crop.color }} />
                      )}
                      {crop?.label ?? t('No data')}
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </Spin>
        )}
      </div>
    </>
  );
}

type CropMapLegendProps = { classes: HistoricalCropClass[]; mixed: boolean };

function CropMapLegend({ classes, mixed }: CropMapLegendProps) {
  const { t } = useTranslation();

  return (
    <ul className="crop-history-legend" aria-label={t('Crop map legend')}>
      {classes.map(({ code, color, label }) => (
        <li key={code}>
          <span className="crop-history-swatch" style={{ background: color }} />
          {label}
        </li>
      ))}
      {mixed && (
        <li>
          <span className="crop-history-swatch crop-history-mixed" />
          {t('No dominant class')}
        </li>
      )}
    </ul>
  );
}

type PointCropPatternsProps = { years: CropHistoryYear[] };

function PointCropPatterns({ years }: PointCropPatternsProps) {
  const { t } = useTranslation();
  const { dominant, observed, occurrences } = summarizeCropPattern(years);
  let summary = t('No mapped crop data at this point.');
  if (dominant) {
    summary = t('{{crop}} mapped in {{occurrences}} of {{observed}} observed years.', {
      crop: dominant.label,
      occurrences,
      observed,
    });
  } else if (observed > 0) {
    summary = t('No class dominated the {{observed}} observed years.', { observed });
  }

  return (
    <div aria-live="polite">
      <p className="crop-history-point-summary">{summary}</p>
      <ul className="crop-history-sequence">
        {years.map(({ year, crop }) => (
          <li key={year}>
            <strong>{year}</strong>
            <span className="crop-history-swatch" style={{ background: crop?.color }} />
            {crop?.label ?? t('No data')}
          </li>
        ))}
      </ul>
    </div>
  );
}

type MapProps = {
  layer: Pick<CropHistoryLayer, 'bounds' | 'image'>;
  showLayer: boolean;
  marker?: CropHistoryPoint;
  rings?: number[][][];
  onPick: (point: CropHistoryPoint) => void;
};

function CropHistoryMap({ layer, showLayer, marker, rings, onPick }: MapProps) {
  const { t } = useTranslation();
  const [west, south, east, north] = layer.bounds;
  const bounds: LatLngBoundsExpression = [
    [south, west],
    [north, east],
  ];
  const pick = ({ latlng }: LeafletMouseEvent) => {
    if (latlng.lng >= west && latlng.lng <= east && latlng.lat >= south && latlng.lat <= north) {
      onPick([latlng.lng, latlng.lat]);
    }
  };

  return (
    <div role="region" aria-label={t('Crop history map')}>
      <MapContainer
        className="crop-history-map"
        bounds={bounds}
        maxZoom={19}
        scrollWheelZoom={false}
      >
        <CropHistoryViewport bounds={layer.bounds} />
        <TileLayer {...satelliteTiles} maxNativeZoom={19} maxZoom={19} />
        {showLayer && layer.image && <ImageOverlay bounds={bounds} url={layer.image} />}
        {rings ? (
          <Polygon
            positions={rings.map((ring) => ring.map(([lon, lat]): LatLngTuple => [lat, lon]))}
            pathOptions={{
              color: '#ffffff',
              weight: 2,
              fillOpacity: 0,
              bubblingMouseEvents: false,
            }}
            eventHandlers={{ click: pick }}
          />
        ) : (
          <MapClick onClick={pick} />
        )}
        {marker && (
          <Marker
            position={[marker[1], marker[0]]}
            icon={pinIcon}
            interactive={false}
            keyboard={false}
          />
        )}
      </MapContainer>
    </div>
  );
}

function CropHistoryViewport({ bounds }: { bounds: CropHistoryLayer['bounds'] }) {
  const map = useMap();
  const [west, south, east, north] = bounds;

  useEffect(() => {
    map.fitBounds(
      [
        [south, west],
        [north, east],
      ],
      { animate: false },
    );
  }, [map, west, south, east, north]);

  return null;
}

function MapClick({ onClick }: { onClick: (event: LeafletMouseEvent) => void }) {
  useMapEvents({ click: onClick });
  return null;
}

function CropHistoryError({ retry }: { retry: () => void }) {
  const { t } = useTranslation();

  return (
    <Alert
      type="warning"
      showIcon
      title={t('Crop history is temporarily unavailable.')}
      action={<Button onClick={retry}>{t('Try again')}</Button>}
    />
  );
}
