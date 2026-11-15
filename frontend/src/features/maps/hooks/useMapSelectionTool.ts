import { circleMarker, layerGroup, polygon, polyline, svg } from 'leaflet';
import { useEffect, useEffectEvent, useState } from 'react';
import { useMap } from 'react-leaflet';
import type { CatalogFeature } from '../../../types/maps/map.types.ts';
import { getLassoFieldIds, isValidLasso, type ScreenPoint } from '../utils/lassoSelection.ts';
import type { SectionCoordinate } from '../utils/sectionSelection.ts';

const controlSelector =
  '.map-selection-controls, .leaflet-control, .map-section-add, .map-section-panel';

export type MapSelectionTool = 'move' | 'lasso' | 'points';

type UseMapSelectionToolOptions = {
  features: CatalogFeature[];
  available: boolean;
  onComplete: (outline: SectionCoordinate[], fields: CatalogFeature[]) => void;
  onToggle: (feature: CatalogFeature) => void;
};

export function useMapSelectionTool({
  features,
  available,
  onComplete,
  onToggle,
}: UseMapSelectionToolOptions) {
  const [tool, setTool] = useState<MapSelectionTool>('move');
  const map = useMap();
  const activeTool = available ? tool : 'move';
  const getFeatures = useEffectEvent(() => features);
  useEffect(() => {
    if (activeTool === 'move') {
      return;
    }
    const container = map.getContainer();
    const handlers = [
      map.dragging,
      map.boxZoom,
      map.doubleClickZoom,
      map.scrollWheelZoom,
      map.touchZoom,
      map.keyboard,
    ];
    const enabledHandlers = handlers.filter((handler) => handler.enabled());
    enabledHandlers.forEach((handler) => handler.disable());
    const oldTouchAction = container.style.touchAction;
    container.style.touchAction = 'none';
    container.classList.add('map-lasso-active');
    const renderer = svg();
    const style = {
      renderer,
      color: '#b9e780',
      weight: 2,
      interactive: false,
    };
    const outline =
      activeTool === 'points'
        ? polyline([], style).addTo(map)
        : polygon([], {
            ...style,
            dashArray: '6 4',
            fillColor: '#8cba5d',
            fillOpacity: 0.18,
          }).addTo(map);
    const vertices = layerGroup().addTo(map);
    let points: ScreenPoint[] = [];
    let anchors: ScreenPoint[] = [];
    let gestureFeatures: CatalogFeature[] = [];
    let pointerId: number | null = null;
    let frame = 0;
    const toPoint = (event: PointerEvent): ScreenPoint => {
      const point = map.mouseEventToContainerPoint(event);
      const size = map.getSize();
      return [Math.max(0, Math.min(size.x, point.x)), Math.max(0, Math.min(size.y, point.y))];
    };
    const isNearFirstPoint = ([x, y]: ScreenPoint) => {
      const first = anchors[0];
      return first !== undefined && Math.hypot(x - first[0], y - first[1]) <= 9;
    };
    const clearClosingCursor = () => container.classList.remove('map-points-close');
    const draw = () => {
      frame = 0;
      outline.setLatLngs(points.map((point) => map.containerPointToLatLng([point[0], point[1]])));
    };
    const resetPointer = () => {
      const released = pointerId;
      pointerId = null;
      if (released !== null && container.hasPointerCapture(released)) {
        container.releasePointerCapture(released);
      }
      points = [];
      cancelAnimationFrame(frame);
      frame = 0;
    };
    const reset = () => {
      resetPointer();
      anchors = [];
      gestureFeatures = [];
      clearClosingCursor();
      vertices.clearLayers();
      outline.setLatLngs([]);
    };
    const finish = (shape: ScreenPoint[]) => {
      const ids = new Set(
        getLassoFieldIds(gestureFeatures, shape, (longitude, latitude) => {
          const point = map.latLngToContainerPoint([latitude, longitude]);
          return [point.x, point.y];
        }),
      );
      const coordinates: SectionCoordinate[] = shape.map(([x, y]) => {
        const location = map.containerPointToLatLng([x, y]);
        return [location.lat, location.lng];
      });
      onComplete(
        coordinates,
        gestureFeatures.filter(
          (feature) => feature.properties.kind === 'field' && ids.has(String(feature.id)),
        ),
      );
      reset();
    };
    const renderAnchors = () => {
      const locations = anchors.map(([x, y]) => map.containerPointToLatLng([x, y]));
      outline.setLatLngs(locations);
      vertices.clearLayers();
      locations.forEach((location, index) => {
        circleMarker(location, {
          ...style,
          radius: index === 0 ? 6 : 4,
          fillColor: '#476b3c',
          fillOpacity: 1,
        }).addTo(vertices);
      });
    };
    const stop = (event: Event) => {
      event.preventDefault();
      event.stopPropagation();
    };
    const down = (event: PointerEvent) => {
      if (
        !event.isPrimary ||
        event.button !== 0 ||
        pointerId !== null ||
        (event.target instanceof Element && event.target.closest(controlSelector))
      ) {
        return;
      }
      stop(event);
      pointerId = event.pointerId;
      points = [toPoint(event)];
      if (!anchors.length) {
        // A background catalog refresh must not change the points in an in-progress selection.
        gestureFeatures = getFeatures();
      }
      container.setPointerCapture(pointerId);
      container.focus({ preventScroll: true });
    };
    const move = (event: PointerEvent) => {
      if (activeTool === 'points' && event.isPrimary) {
        const overControl =
          event.target instanceof Element && event.target.closest(controlSelector);
        container.classList.toggle(
          'map-points-close',
          !overControl && isNearFirstPoint(toPoint(event)) && isValidLasso(anchors),
        );
      }
      if (event.pointerId !== pointerId) {
        return;
      }
      stop(event);
      if (activeTool === 'points') {
        return;
      }
      const point = toPoint(event);
      const previous = points[points.length - 1];
      if (Math.hypot(point[0] - previous[0], point[1] - previous[1]) < 3) {
        return;
      }
      points.push(point);
      if (points.length > 512) {
        points = points.filter((_, index) => index % 2 === 0 || index === points.length - 1);
      }
      if (!frame) {
        frame = requestAnimationFrame(draw);
      }
    };
    const up = (event: PointerEvent) => {
      if (event.pointerId !== pointerId) {
        return;
      }
      stop(event);
      const end = toPoint(event);
      const start = points[0];
      if (activeTool === 'points') {
        resetPointer();
        if (Math.hypot(end[0] - start[0], end[1] - start[1]) > 6) {
          return;
        }
        if (isNearFirstPoint(end)) {
          if (isValidLasso(anchors)) {
            finish(anchors);
          }
          return;
        }
        if (anchors.length < 512) {
          anchors.push(end);
          renderAnchors();
        }
        return;
      }
      points.push(end);
      const isClick = points.every(
        (point) => Math.hypot(point[0] - start[0], point[1] - start[1]) <= 6,
      );
      if (isClick) {
        let nearest: CatalogFeature | undefined;
        let nearestDistance = 9;
        for (const feature of gestureFeatures) {
          if (feature.properties.kind !== 'field' || feature.id === undefined) {
            continue;
          }
          const [longitude, latitude] = feature.geometry.coordinates;
          const point = map.latLngToContainerPoint([latitude, longitude]);
          const distance = Math.hypot(point.x - start[0], point.y - start[1]);
          if (distance < nearestDistance) {
            nearestDistance = distance;
            nearest = feature;
          }
        }
        if (nearest) {
          onToggle(nearest);
        }
      } else if (isValidLasso(points)) {
        finish(points);
        return;
      }
      reset();
    };
    const cancelPointer = (event: PointerEvent) => {
      if (pointerId === event.pointerId) {
        reset();
      }
    };
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        stop(event);
        reset();
        setTool('move');
      } else if (activeTool === 'points' && event.target === container && pointerId === null) {
        if (event.key === 'Enter' && isValidLasso(anchors)) {
          stop(event);
          finish(anchors);
        } else if (event.key === 'Backspace' && anchors.length) {
          stop(event);
          anchors.pop();
          clearClosingCursor();
          renderAnchors();
        }
      }
    };
    const click = (event: MouseEvent) => {
      if (!(event.target instanceof Element && event.target.closest(controlSelector))) {
        stop(event);
      }
    };
    container.addEventListener('pointerdown', down, true);
    container.addEventListener('pointermove', move, true);
    container.addEventListener('pointerleave', clearClosingCursor);
    container.addEventListener('pointerup', up, true);
    container.addEventListener('pointercancel', cancelPointer, true);
    container.addEventListener('lostpointercapture', cancelPointer, true);
    container.addEventListener('click', click, true);
    container.addEventListener('keydown', keydown, true);
    window.addEventListener('blur', reset);
    map.on('movestart resize', reset);
    return () => {
      reset();
      container.removeEventListener('pointerdown', down, true);
      container.removeEventListener('pointermove', move, true);
      container.removeEventListener('pointerleave', clearClosingCursor);
      container.removeEventListener('pointerup', up, true);
      container.removeEventListener('pointercancel', cancelPointer, true);
      container.removeEventListener('lostpointercapture', cancelPointer, true);
      container.removeEventListener('click', click, true);
      container.removeEventListener('keydown', keydown, true);
      window.removeEventListener('blur', reset);
      map.off('movestart resize', reset);
      vertices.remove();
      outline.remove();
      renderer.remove();
      container.style.touchAction = oldTouchAction;
      container.classList.remove('map-lasso-active');
      enabledHandlers.forEach((handler) => handler.enable());
    };
  }, [map, activeTool, onComplete, onToggle]);

  return { activeTool, setTool };
}
