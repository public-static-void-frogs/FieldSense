import { latLngBounds, type Map as LeafletMap } from 'leaflet';
import type { SectionMapImage } from '../../../api/section-analysis/section-analysis.api.ts';
import type { MapSection } from './sectionSelection.ts';

export class MapCaptureError extends Error {}

function loadTile(source: string, signal: AbortSignal): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    signal.throwIfAborted();
    const image = new Image();
    image.crossOrigin = 'anonymous';
    const cleanup = () => {
      signal.removeEventListener('abort', abort);
      image.onload = null;
      image.onerror = null;
    };
    const abort = () => {
      cleanup();
      image.src = '';
      reject(signal.reason);
    };
    image.onload = () => {
      cleanup();
      resolve(image);
    };
    image.onerror = () => {
      cleanup();
      reject(new MapCaptureError('Map imagery could not be loaded'));
    };
    signal.addEventListener('abort', abort, { once: true });
    image.src = source;
  });
}

/** Composite the displayed satellite tiles only, preserving the image's geographic extent. */
export async function captureSectionImage(
  map: LeafletMap,
  section: MapSection,
  signal: AbortSignal,
): Promise<SectionMapImage> {
  try {
    const container = map.getContainer();
    const panel = container.querySelector('.map-section-panel')?.getBoundingClientRect();
    const size = map.getSize();
    const mobile = panel && panel.width > size.x * 0.7;
    const leftPanel =
      panel && !mobile && panel.left < container.getBoundingClientRect().left + size.x / 2;
    map.fitBounds(latLngBounds(section.outline), {
      animate: false,
      paddingTopLeft: [leftPanel ? (panel?.width ?? 0) + 48 : 32, 72],
      paddingBottomRight: mobile
        ? [32, (panel?.height ?? 0) + 40]
        : [leftPanel ? 32 : (panel?.width ?? 0) + 48, 40],
    });
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
    signal.throwIfAborted();
    const extent = latLngBounds(section.outline);
    const northwest = map.latLngToContainerPoint(extent.getNorthWest());
    const southeast = map.latLngToContainerPoint(extent.getSouthEast());
    const left = Math.max(0, Math.floor(northwest.x));
    const top = Math.max(0, Math.floor(northwest.y));
    const right = Math.min(size.x, Math.ceil(southeast.x));
    const bottom = Math.min(size.y, Math.ceil(southeast.y));
    const width = right - left;
    const height = bottom - top;
    if (width <= 0 || height <= 0) {
      throw new MapCaptureError('Section is outside the map');
    }
    const nw = map.containerPointToLatLng([left, top]);
    const se = map.containerPointToLatLng([right, bottom]);
    const scale = Math.min(1, 1536 / Math.max(width, height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(width * scale));
    canvas.height = Math.max(1, Math.round(height * scale));
    const context = canvas.getContext('2d');
    if (!context) {
      throw new MapCaptureError('Canvas is unavailable');
    }
    const origin = container.getBoundingClientRect();
    const tiles = [
      ...container.querySelectorAll<HTMLImageElement>('.leaflet-tile-pane img.leaflet-tile'),
    ]
      .map((tile) => ({
        source: tile.currentSrc || tile.src,
        rect: tile.getBoundingClientRect(),
        level: Number(tile.parentElement?.style.zIndex || 0),
      }))
      .filter(
        ({ rect }) =>
          rect.width > 0 &&
          rect.height > 0 &&
          rect.right > origin.left + left &&
          rect.left < origin.left + right &&
          rect.bottom > origin.top + top &&
          rect.top < origin.top + bottom,
      );
    if (!tiles.length) {
      throw new MapCaptureError('Map imagery is not ready');
    }
    // Use the current zoom's tile container rather than cached fading zoom levels.
    const level = Math.max(...tiles.map((tile) => tile.level));
    const visibleTiles = tiles.filter((tile) => tile.level === level);
    const captureSignal = AbortSignal.any([signal, AbortSignal.timeout(8000)]);
    const images = await Promise.all(
      visibleTiles.map((tile) => loadTile(tile.source, captureSignal)),
    );
    signal.throwIfAborted();
    visibleTiles.forEach(({ rect }, index) =>
      context.drawImage(
        images[index],
        (rect.left - origin.left - left) * scale,
        (rect.top - origin.top - top) * scale,
        rect.width * scale,
        rect.height * scale,
      ),
    );

    return {
      dataUrl: canvas.toDataURL('image/png'),
      crs: 'EPSG:3857',
      width: canvas.width,
      height: canvas.height,
      bounds: [nw.lng, se.lat, se.lng, nw.lat],
    };
  } catch (error) {
    signal.throwIfAborted();
    throw new MapCaptureError('Map imagery could not be captured', { cause: error });
  }
}
