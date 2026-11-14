import { weatherScenes } from '../constants/weatherScenes.constants.ts';

export function getWeatherScene(conditions: string) {
  if (Object.hasOwn(weatherScenes, conditions)) {
    return weatherScenes[conditions];
  }
  return weatherScenes['Unknown conditions'];
}
