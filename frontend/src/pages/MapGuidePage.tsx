import { Collapse } from 'antd';
import { ArrowLeft, Play, Square } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation } from 'react-router-dom';
import { RouterButton } from '../components/common/RouterButton';
import { mapGuideQuestions, mapGuideSteps } from '../features/maps/constants/mapGuide.constants.ts';
import '../features/maps/components/MapGuide.css';

export function MapGuidePage() {
  const { t } = useTranslation();
  const { state } = useLocation();
  const mapPath = state?.mapPath === '/map/add' ? '/map/add' : '/map';
  const search = typeof state?.mapSearch === 'string' ? state.mapSearch : '';
  const mapDestination = { pathname: mapPath, search };

  return (
    <article className="map-guide">
      <RouterButton
        className="map-guide-back"
        type="link"
        to={mapDestination}
        icon={<ArrowLeft size={16} />}
      >
        {t('Back to the map')}
      </RouterButton>
      <header className="map-guide-intro">
        <h1>{t('Field Map guide')}</h1>
        <p>
          {t('Find fields on the map, draw a section, and save the crop areas you want to keep.')}
        </p>
      </header>
      <ol className="map-guide-steps">
        {mapGuideSteps.map(({ id, icon: Icon, title, instructions, demoDescription }, index) => (
          <li className="map-guide-step" key={id}>
            <div className="map-guide-instructions">
              <h2>
                <Icon size={21} aria-hidden />
                {index + 1}. {t(title)}
              </h2>
              {instructions.map((instruction) => (
                <p key={instruction}>{t(instruction)}</p>
              ))}
            </div>
            <MapGuideDemo id={id} description={demoDescription} />
          </li>
        ))}
      </ol>
      <section className="map-guide-questions" aria-labelledby="map-guide-questions">
        <h2 id="map-guide-questions">{t('Common questions')}</h2>
        <Collapse
          defaultActiveKey={['imagery']}
          items={mapGuideQuestions.map(({ id, question, answer }) => ({
            key: id,
            label: t(question),
            children: t(answer),
          }))}
        />
      </section>
    </article>
  );
}

type MapGuideDemoProps = { id: (typeof mapGuideSteps)[number]['id']; description: string };

function MapGuideDemo({ id, description }: MapGuideDemoProps) {
  const { t, i18n } = useTranslation();
  const [playing, setPlaying] = useState(false);
  const localized = id !== 'move' && i18n.resolvedLanguage === 'uk' ? '-uk' : '';
  const asset = `${import.meta.env.BASE_URL}images/map-guide/${id}${localized}`;

  return (
    <figure className="map-guide-demo">
      <img
        src={playing ? `${asset}.gif` : `${asset}.png`}
        alt={t(description)}
        width={576}
        height={324}
        loading="lazy"
      />
      <button type="button" className="map-guide-play" onClick={() => setPlaying(!playing)}>
        {playing ? <Square size={14} aria-hidden /> : <Play size={14} aria-hidden />}
        {playing ? t('Stop demo') : t('Play demo')}
      </button>
    </figure>
  );
}
