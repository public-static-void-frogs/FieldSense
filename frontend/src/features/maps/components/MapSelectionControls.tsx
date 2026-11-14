import { Button, Tooltip } from 'antd';
import { useRef } from 'react';
import { Hand, LassoSelect, PenTool } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { MapSelectionTool } from '../hooks/useMapSelectionTool.ts';
import { useMapControlEvents } from '../hooks/useMapControlEvents.ts';

type MapSelectionControlsProps = {
  count: number;
  activeTool: MapSelectionTool;
  canSelect: boolean;
  onSelectTool: (tool: MapSelectionTool) => void;
};

export function MapSelectionControls({
  count,
  activeTool,
  canSelect,
  onSelectTool,
}: MapSelectionControlsProps) {
  const { t } = useTranslation();
  const control = useRef<HTMLElement>(null);
  useMapControlEvents(control);
  const zoomHint = t('Zoom in until individual field points are visible to select fields.');
  const tools = [
    { id: 'move', label: t('Move map'), icon: Hand },
    { id: 'lasso', label: t('Lasso selection'), icon: LassoSelect },
    { id: 'points', label: t('Point selection'), icon: PenTool },
  ] as const;

  return (
    <section ref={control} className="map-selection-controls" aria-label={t('Selection tools')}>
      {tools.map(({ id, label, icon: Icon }) => {
        const disabled = id !== 'move' && !canSelect;
        let title = label;
        if (disabled) {
          title = zoomHint;
        } else if (id === 'points') {
          title = t('Point selection. Click to add points, then click the first point to close.');
        }

        return (
          <Tooltip key={id} title={title}>
            <span>
              <Button
                icon={<Icon size={17} />}
                type={activeTool === id ? 'primary' : 'text'}
                aria-label={label}
                aria-pressed={activeTool === id}
                disabled={disabled}
                onClick={() => onSelectTool(id)}
              />
            </span>
          </Tooltip>
        );
      })}
      <span className="map-selection-status" role="status" aria-live="polite" aria-atomic="true">
        {t('{{count}} fields selected', { count })}
      </span>
    </section>
  );
}
