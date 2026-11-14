import { Alert, Button, Checkbox, Progress } from 'antd';
import { Plus, ScanLine, X } from 'lucide-react';
import { useSaveCropAreas } from '../hooks/useSaveCropAreas.ts';
import { useTranslation } from 'react-i18next';
import { useMapControlEvents } from '../hooks/useMapControlEvents.ts';
import { useSectionFocus } from '../hooks/useSectionFocus.ts';
import { useSectionAnalysis, type SectionAnalysisActions } from '../hooks/useSectionAnalysis.ts';
import type { AnalysisProgress } from '../../../api/section-analysis/section-analysis.api.ts';
import type { CropZone } from '../../../types/maps/map.types.ts';
import {
  groupSectionCrops,
  includedCropZones,
  sectionArea,
  type MapSection,
} from '../utils/sectionSelection.ts';
import { detectedCropIcons } from '../constants/maps.constants.ts';

type SectionPanelProps = {
  section: MapSection;
  onCancel: (id: string) => void;
  onSelectCrop: (sectionId: string, crop: CropZone['crop'], included: boolean) => void;
  analysisActions: SectionAnalysisActions;
};

export function SectionPanel({
  section,
  onCancel,
  onSelectCrop,
  analysisActions,
}: SectionPanelProps) {
  const { t, i18n } = useTranslation();
  const panel = useSectionFocus(section);
  useMapControlEvents(panel);
  const { analyze, progress } = useSectionAnalysis(section, analysisActions);
  const number = new Intl.NumberFormat(i18n.language, { maximumFractionDigits: 1 });
  const complete = section.analysisStatus === 'complete';
  const skippedCount = section.skippedCount ?? 0;
  const pending = section.analysisStatus === 'pending';
  const crops = groupSectionCrops(section);
  const included = includedCropZones(section);
  const { save, saving, saveError } = useSaveCropAreas(included, () => onCancel(section.id));
  const count = complete ? included.length : section.fields.length;
  const area = complete
    ? included.reduce((total, field) => total + field.areaHa, 0)
    : sectionArea(section);

  return (
    <aside
      ref={panel}
      className="map-section-panel map-section-interactive"
      aria-label={t('Section details')}
      aria-busy={pending}
    >
      <h2>{t('Section overview')}</h2>
      <dl className="map-section-parameters">
        <div>
          <dt>{complete ? t('Selected crop areas') : t('Selected fields')}</dt>
          <dd>{number.format(count)}</dd>
        </div>
        <div>
          <dt>{t('Approximate area')}</dt>
          <dd>{t('About {{area}} ha', { area: number.format(area) })}</dd>
        </div>
      </dl>
      {complete && (
        <div className="map-detected-fields" aria-label={t('Crop types')}>
          {crops.map((group) => (
            <div key={group.crop} className="map-detected-field">
              <Checkbox
                checked={group.selected === group.total}
                indeterminate={group.selected > 0 && group.selected < group.total}
                aria-label={t('{{crop}}: {{selected}} of {{total}} areas selected', {
                  crop: group.crop,
                  selected: group.selected,
                  total: group.total,
                })}
                onChange={(event) => onSelectCrop(section.id, group.crop, event.target.checked)}
              >
                <span className="map-detected-crop" aria-hidden="true">
                  {detectedCropIcons[group.crop] ?? '🌱'}
                </span>
                <span className="map-detected-crop-name">{group.crop}</span>
                <span className="map-crop-group-count">
                  {group.selected}/{group.total}
                </span>
              </Checkbox>
            </div>
          ))}
        </div>
      )}
      {complete && skippedCount > 0 && (
        <Alert type="warning" title={t('Fields skipped ({{count}})', { count: skippedCount })} />
      )}
      {saveError && <Alert type="error" title={t('Unable to save crop areas. Try again.')} />}
      {section.analysisError && <Alert type="error" title={section.analysisError} />}
      {pending && <SectionAnalysisProgress progress={progress} />}
      <div className="map-section-actions">
        {complete ? (
          <Button
            type="primary"
            block
            disabled={!count}
            loading={saving}
            icon={<Plus size={16} />}
            onClick={save}
          >
            {t('Add areas')}
          </Button>
        ) : (
          <Button
            type="primary"
            block
            loading={pending}
            icon={<ScanLine size={16} />}
            onClick={analyze}
          >
            {t('Analyze')}
          </Button>
        )}
        <Button block disabled={saving} icon={<X size={16} />} onClick={() => onCancel(section.id)}>
          {t('Cancel section')}
        </Button>
      </div>
    </aside>
  );
}

type SectionAnalysisProgressProps = { progress?: AnalysisProgress };

function SectionAnalysisProgress({ progress }: SectionAnalysisProgressProps) {
  const { t } = useTranslation();
  const labels = {
    segmentation: t('Finding field boundaries'),
    satellite: t('Processing satellite observations'),
    classification: t('Classifying crops'),
  };
  const label = progress ? labels[progress.stage] : t('Preparing map imagery');
  const ranges = {
    segmentation: { start: 0, span: 10 },
    satellite: { start: 10, span: 85 },
    classification: { start: 95, span: 5 },
  };
  let percent = 0;
  if (progress) {
    const { start, span } = ranges[progress.stage];
    const fraction = progress.total ? progress.completed / progress.total : 0;
    percent = Math.floor(start + span * fraction);
  }

  return (
    <div>
      <div aria-live="polite">{label}</div>
      <Progress aria-label={label} percent={percent} size="small" status="active" />
    </div>
  );
}
