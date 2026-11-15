import { useSuspenseQueries } from '@tanstack/react-query';
import { Button, Dropdown, Modal, Result, Space } from 'antd';
import { ArrowLeft, ListOrdered, MapPin, Pencil, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link, useLoaderData, useLocation, useNavigate } from 'react-router-dom';
import { fieldQueries } from '../api/fields/fields.queries.ts';
import type { FieldRouteData } from '../app/route-loaders.ts';
import { CropIcon } from '../components/common/CropIcon';
import { PageHeading } from '../components/common/PageHeading';
import { RouterButton } from '../components/common/RouterButton';
import { FieldAssistant } from '../features/assistant/components/FieldAssistant';
import { FieldCropHistory } from '../features/fields/components/FieldCropHistory';
import { FieldM2Insights } from '../features/fields/components/FieldM2Insights';
import { FieldM3Insights } from '../features/fields/components/FieldM3Insights';
import { FieldProperties } from '../features/fields/components/FieldProperties';
import { FieldRecommendation } from '../features/fields/components/FieldRecommendation';
import { FieldStatus } from '../features/fields/components/FieldStatus';
import { useFieldRemoval } from '../features/fields/hooks/useFieldRemoval.ts';
import { FieldMap } from '../features/maps/components/FieldMap';
import { useFieldLocation } from '../features/maps/hooks/useFieldLocation.ts';
import { recommendationPath } from '../features/rotation/utils/rotationRoutes.ts';
import { useDemoMode } from '../features/demo/hooks/useDemoMode.ts';

const sections = {
  map: { id: 'field-location-map', label: 'Location map' },
  properties: { id: 'field-properties', label: 'Field properties' },
  recommendations: { id: 'crop-recommendations', label: 'Crop strategies for next season' },
  history: { id: 'crop-history', label: 'Crop history' },
  timing: { id: 'crop-timing-and-climate-risk', label: 'Crop timing and climate risk' },
  evidence: { id: 'neighbour-evidence', label: 'Neighbour evidence' },
} as const;

export function FieldDetailsPage() {
  const { t } = useTranslation();
  const demo = useDemoMode();
  const navigate = useNavigate();
  const { search } = useLocation();
  const { fieldId } = useLoaderData<FieldRouteData>();
  const [{ data: field }, { data: propertyData }] = useSuspenseQueries({
    queries: [fieldQueries.byId(fieldId), fieldQueries.properties(fieldId)],
  });
  const geojson = useFieldLocation(fieldId);
  const { confirmRemove, setConfirmRemove, isRemovingField, handleRemove } =
    useFieldRemoval(fieldId);
  if (!field) {
    return <FieldNotFound />;
  }

  return (
    <>
      <PageHeading
        title={demo ? field.name : field.crop || field.name}
        eyebrow=""
        titlePrefix={
          <>
            <RouterButton
              type="text"
              icon={<ArrowLeft size={20} />}
              aria-label={t('Back to my fields')}
              to="/fields"
            />
            {field.crop && <CropIcon crop={field.crop} size={36} />}
          </>
        }
        actions={
          <Space wrap>
            {field.status && <FieldStatus status={field.status} />}
            <FieldAssistant key={field.id} field={field} />
            <RouterButton
              type="primary"
              icon={<ListOrdered size={19} />}
              to={recommendationPath(field.id)}
            >
              {t('Crop recommendation')}
            </RouterButton>
            {!demo && (
              <Dropdown
                trigger={['click']}
                menu={{
                  items: [
                    {
                      key: 'map',
                      icon: <MapPin size={16} />,
                      label: t('Explore farm map'),
                      onClick: () => navigate('/map'),
                    },
                    {
                      key: 'remove',
                      danger: true,
                      icon: <Trash2 size={16} />,
                      label: t('Remove field'),
                      onClick: () => setConfirmRemove(true),
                    },
                  ],
                }}
              >
                <Button icon={<Pencil size={17} />}>{t('Edit')}</Button>
              </Dropdown>
            )}
          </Space>
        }
      />
      <nav className="field-detail-nav" aria-label={t('On this page')}>
        <span className="field-detail-nav-label">{t('On this page')}</span>
        <ul>
          {Object.values(sections)
            .filter((section) => section !== sections.properties || propertyData)
            .map(({ id, label }) => (
              <li key={id}>
                <Link to={{ search, hash: `#${id}` }}>{t(label)}</Link>
              </li>
            ))}
        </ul>
      </nav>
      <div
        id={sections.map.id}
        className="field-detail-map field-detail-anchor"
        aria-label={t('{{value0}} location map', { value0: field.name })}
      >
        <FieldMap
          fields={[field]}
          geojson={geojson}
          locationOnly
          hideControls
          adding={false}
          onSelect={(selected) => navigate(`/fields/${selected.id}`)}
          onAdd={() => navigate('/map/add')}
        />
      </div>
      <div className="field-detail-stack">
        {propertyData && (
          <div className="field-detail-anchor" id={sections.properties.id}>
            <FieldProperties field={field} data={propertyData} />
          </div>
        )}
        <div className="field-detail-anchor" id={sections.recommendations.id}>
          <FieldRecommendation fieldId={field.id} />
        </div>
        <div className="field-detail-anchor" id={sections.history.id}>
          <FieldCropHistory key={field.id} field={field} />
        </div>
        <div className="field-detail-anchor" id={sections.timing.id}>
          <FieldM3Insights field={field} />
        </div>
        <div className="field-detail-anchor" id={sections.evidence.id}>
          <FieldM2Insights field={field} />
        </div>
      </div>
      <Modal
        open={confirmRemove}
        title={t('Remove {{value0}}?', { value0: field.name })}
        okText={t('Confirm removal')}
        cancelText={t('Keep field')}
        okButtonProps={{ danger: true }}
        cancelButtonProps={{ disabled: isRemovingField }}
        closable={!isRemovingField}
        confirmLoading={isRemovingField}
        onOk={handleRemove}
        onCancel={() => {
          if (!isRemovingField) {
            setConfirmRemove(false);
          }
        }}
      >
        {t('Your field will leave the farm list.')}
      </Modal>
    </>
  );
}

function FieldNotFound() {
  const { t } = useTranslation();

  return (
    <Result
      status="404"
      title={t('Field not found')}
      subTitle={t('This field may have been removed from your farm.')}
      extra={
        <RouterButton type="primary" to="/fields">
          {t('Back to my fields')}
        </RouterButton>
      }
    />
  );
}
