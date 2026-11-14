import type { CSSProperties } from 'react';
import { getWeatherScene } from '../utils/weatherScene.ts';
import './WeatherScene.css';

type WeatherSceneProps = { conditions: string };

export function WeatherScene({ conditions }: WeatherSceneProps) {
  const scene = getWeatherScene(conditions);

  return (
    <div className={`weather-scene weather-scene--${scene.name}`} aria-hidden="true">
      {scene.sun && <div className="weather-scene-sun" />}
      {Array.from({ length: scene.clouds }, (_, index) => (
        <span
          key={`cloud-${index}`}
          className="weather-scene-cloud"
          style={{ '--cloud-index': index } as CSSProperties}
        />
      ))}
      {scene.name === 'fog' && (
        <div className="weather-scene-fog">
          <span />
          <span />
          <span />
        </div>
      )}
      {scene.precipitation && (
        <div className={`weather-scene-precipitation weather-scene-${scene.precipitation}`}>
          {Array.from({ length: scene.particles }, (_, index) => {
            const duration = scene.duration * (0.75 + ((index * 7) % 10) / 20);

            return (
              <span
                key={index}
                className="weather-scene-particle"
                style={
                  {
                    '--particle-left': `${(index * 37 + 3) % 100}%`,
                    '--particle-duration': `${duration}s`,
                    '--particle-delay': `${-((index * 13) % 30) / 3}s`,
                    '--particle-opacity': 0.25 + ((index * 3) % 7) / 10,
                    '--particle-size': `${3 + (index % 4)}px`,
                    '--particle-drift': `${-25 - (index % 5) * 8}px`,
                  } as CSSProperties
                }
              >
                <i />
              </span>
            );
          })}
        </div>
      )}
      {scene.name === 'storm' && (
        <svg className="weather-scene-lightning" viewBox="0 0 160 260" fill="none">
          <path d="m106 4-63 115h47L43 252l89-156H87l39-92" />
        </svg>
      )}
      {scene.name === 'unknown' && <div className="weather-scene-neutral" />}
    </div>
  );
}
