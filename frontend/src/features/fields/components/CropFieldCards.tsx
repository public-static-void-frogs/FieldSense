import { ArrowRight, MapPin } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import type { Field } from '../../../types/fields/field.types.ts';
import { FarmlandBackdrop } from '../../../components/common/FarmlandBackdrop';
import { RouterButton } from '../../../components/common/RouterButton';
import { CropIllustration } from './CropIllustration.tsx';
import './CropFieldCards.css';

type CropFieldCardsProps = { fields: Field[]; compact?: boolean };

export function CropFieldCards({ fields, compact = false }: CropFieldCardsProps) {
  const { t, i18n } = useTranslation();
  const number = new Intl.NumberFormat(i18n.resolvedLanguage, { maximumFractionDigits: 1 });

  if (!fields.length) {
    return (
      <section
        className={compact ? 'crop-field-empty crop-field-empty--compact' : 'crop-field-empty'}
        aria-labelledby="crop-field-empty-title"
      >
        <FarmlandBackdrop />
        <div className="crop-field-empty-content">
          <h2 id="crop-field-empty-title">{t('Add your first field')}</h2>
          <p>{t('Choose your fields on the map to start tracking crop conditions.')}</p>
          <RouterButton type="primary" size="large" icon={<MapPin size={18} />} to="/map/add">
            {t('Add fields')}
          </RouterButton>
        </div>
      </section>
    );
  }

  return (
    <ul className={compact ? 'crop-field-list crop-field-list--compact' : 'crop-field-list'}>
      {fields.map((field) => (
        <li key={field.id}>
          <Link className="crop-field-card" to={`/fields/${field.id}`}>
            <CropIllustration crop={field.crop} />
            <div className="crop-field-card-copy">
              <h2>{field.crop ?? t('Not supplied')}</h2>
              <p>{t('{{value0}} ha', { value0: number.format(field.area) })}</p>
            </div>
            <ArrowRight className="crop-field-card-arrow" size={21} aria-hidden="true" />
          </Link>
        </li>
      ))}
    </ul>
  );
}
