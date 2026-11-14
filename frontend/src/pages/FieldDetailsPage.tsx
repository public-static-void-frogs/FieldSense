import { useSuspenseQueries } from '@tanstack/react-query';
import { Button, Dropdown, Modal, Result, Space } from 'antd';
import { ArrowLeft, MapPin, Pencil, Sprout, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useLoaderData, useNavigate } from 'react-router-dom';
import { fieldQueries } from '../api/fields/fields.queries.ts';
import type { FieldRouteData } from '../app/route-loaders.ts';
import { PageHeading } from '../components/common/PageHeading';
import { RouterButton } from '../components/common/RouterButton';
import { CropRotationPlan } from '../features/fields/components/CropRotationPlan';
import { FieldCropHistory } from '../features/fields/components/FieldCropHistory';
import { FieldProperties } from '../features/fields/components/FieldProperties';
import { FieldRecommendation } from '../features/fields/components/FieldRecommendation';
import { FieldStatus } from '../features/fields/components/FieldStatus';
import { useFieldRemoval } from '../features/fields/hooks/useFieldRemoval.ts';
import { FieldMap } from '../features/maps/components/FieldMap';
import { useFieldLocation } from '../features/maps/hooks/useFieldLocation.ts';

export function FieldDetailsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
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
        title={field.crop || field.name}
        eyebrow=""
        titlePrefix={
          <RouterButton
            type="text"
            icon={<ArrowLeft size={20} />}
            aria-label={t('Back to my fields')}
            to="/fields"
          />
        }
        actions={
          <Space wrap>
            {field.status && <FieldStatus status={field.status} />}
            {propertyData && field.crop && (
              <RouterButton
                type="primary"
                icon={<Sprout size={19} />}
                to={`/fields/${field.id}/strategy`}
              >
                {t('Rotation strategy')}
              </RouterButton>
            )}
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
          </Space>
        }
      />
      <div
        className="field-detail-map"
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
        <CropRotationPlan field={field} />
        <FieldRecommendation field={field} />
        <FieldProperties field={field} />
        <FieldCropHistory key={field.id} field={field} />
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
