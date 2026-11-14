export type WeatherSceneConfig = {
  name:
    | 'clear'
    | 'partly-cloudy'
    | 'overcast'
    | 'fog'
    | 'drizzle'
    | 'rain'
    | 'snow'
    | 'storm'
    | 'unknown';
  sun: boolean;
  clouds: number;
  precipitation: 'rain' | 'snow' | null;
  particles: number;
  duration: number;
};

export const weatherScenes: Record<string, WeatherSceneConfig> = {
  'Clear sky': {
    name: 'clear',
    sun: true,
    clouds: 0,
    precipitation: null,
    particles: 0,
    duration: 0,
  },
  'Partly cloudy': {
    name: 'partly-cloudy',
    sun: true,
    clouds: 2,
    precipitation: null,
    particles: 0,
    duration: 0,
  },
  Overcast: {
    name: 'overcast',
    sun: false,
    clouds: 4,
    precipitation: null,
    particles: 0,
    duration: 0,
  },
  Fog: { name: 'fog', sun: false, clouds: 0, precipitation: null, particles: 0, duration: 0 },
  Drizzle: {
    name: 'drizzle',
    sun: false,
    clouds: 2,
    precipitation: 'rain',
    particles: 20,
    duration: 2.8,
  },
  Rain: {
    name: 'rain',
    sun: false,
    clouds: 3,
    precipitation: 'rain',
    particles: 42,
    duration: 1.3,
  },
  Snow: { name: 'snow', sun: false, clouds: 2, precipitation: 'snow', particles: 30, duration: 9 },
  Thunderstorm: {
    name: 'storm',
    sun: false,
    clouds: 4,
    precipitation: 'rain',
    particles: 48,
    duration: 0.9,
  },
  'Unknown conditions': {
    name: 'unknown',
    sun: false,
    clouds: 0,
    precipitation: null,
    particles: 0,
    duration: 0,
  },
};
