import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Card, ConfigProvider, Empty, Select, Slider, Spin, theme } from 'antd';
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
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import { cropHistoryQueries } from '../../../api/fields/crop-history.queries.ts';
import type {
  CropHistoryLayer,
  CropHistoryPoint,
  CropLayerClass,
} from '../../../types/fields/crop-history.types.ts';
import type { Field } from '../../../types/fields/field.types.ts';
import { satelliteTiles } from '../../maps/constants/maps.constants.ts';
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

export function FieldCropHistory({ field }: { field: Field }) {
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
  const [year, setYear] = useState<number>();
  const [previewIndex, setPreviewIndex] = useState<number | null>(null);
  const point = pin?.scope === scope ? pin.point : null;
  const history = useQuery(cropHistoryQueries.point(fieldId, part, geometryKey, point));
  const selectedYear = year ?? history.data?.years[0]?.year;
  const layer = useQuery(cropHistoryQueries.layer(fieldId, part, geometryKey, selectedYear));
  const chronologicalYears = history.data?.years.map(({ year }) => year).reverse() ?? [];
  const marker = point ?? (history.isPlaceholderData ? undefined : history.data?.coordinates);
  const lastIndex = chronologicalYears.length - 1;
  const sliderIndex = previewIndex ?? chronologicalYears.findIndex((year) => year === selectedYear);
  const yearMarks = Object.fromEntries(
    [0, Math.floor(lastIndex / 2), lastIndex].map((index) => [index, chronologicalYears[index]]),
  );

  return (
    <>
      <div className="crop-history-main">
        <Spin spinning={layer.isFetching || (selectedYear === undefined && history.isFetching)}>
          {layer.data ? (
            <div
              className={layer.isPlaceholderData ? 'crop-history-placeholder' : undefined}
              inert={layer.isPlaceholderData}
            >
              <CropHistoryMap
                layer={layer.data}
                showLayer={!layer.isPlaceholderData && !layer.isError}
                marker={marker}
                rings={rings}
                onPick={(point) => setPin({ scope, point })}
              />
            </div>
          ) : (
            <div className="crop-history-map" />
          )}
        </Spin>
        {chronologicalYears.length > 0 && (
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
        {layer.isError && <CropHistoryError retry={() => void layer.refetch()} />}
        {selectedYear !== undefined && layer.data && layer.data.classes.length > 0 && (
          <div className={layer.isPlaceholderData ? 'crop-history-placeholder' : undefined}>
            <CropShareChart year={selectedYear} classes={layer.data.classes} />
          </div>
        )}
        {layer.data && !layer.data.image && (
          <div className={layer.isPlaceholderData ? 'crop-history-placeholder' : undefined}>
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={t('No mapped crop data for this year.')}
            />
          </div>
        )}
        <p>{t('Tap the map to see the crop history at that spot.')}</p>
        <small>{t('Source')} · USDA Cropland Data Layer</small>
      </div>
      <div className="crop-history-list">
        <h3>{t('History at map pin')}</h3>
        {history.isError && <CropHistoryError retry={() => void history.refetch()} />}
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
      </div>
    </>
  );
}

function CropShareChart({ year, classes }: { year: number; classes: CropLayerClass[] }) {
  const { t, i18n } = useTranslation();
  const { token } = theme.useToken();
  const percent = new Intl.NumberFormat(i18n.language, {
    style: 'percent',
    maximumFractionDigits: 1,
  });
  const ranked = [...classes].sort((a, b) => b.share - a.share);
  const maxEntries = 6;
  const data =
    ranked.length <= maxEntries
      ? ranked
      : [
          ...ranked.slice(0, maxEntries - 1),
          {
            code: 'other',
            label: t('Other'),
            color: token.colorTextTertiary,
            share: ranked.slice(maxEntries - 1).reduce((sum, crop) => sum + crop.share, 0),
          },
        ];

  return (
    <section className="crop-history-share">
      <h3>{t('Crop share in {{year}}', { year })}</h3>
      <p>{t('Share of classified pixels in the displayed area')}</p>
      <div className="crop-history-share-content">
        <div className="crop-history-pie">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart accessibilityLayer>
              <Pie
                data={data}
                dataKey="share"
                nameKey="label"
                outerRadius="94%"
                isAnimationActive={false}
              >
                {data.map((crop) => (
                  <Cell key={crop.code} fill={crop.color} />
                ))}
              </Pie>
              <Tooltip formatter={(value) => percent.format(Number(value))} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <ul>
          {data.map((crop) => (
            <li key={crop.code}>
              <span className="crop-history-swatch" style={{ background: crop.color }} />
              <span>{crop.label}</span>
              <strong>{percent.format(crop.share)}</strong>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

type MapProps = {
  layer: CropHistoryLayer;
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
