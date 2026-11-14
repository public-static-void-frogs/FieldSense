import type { CircleMarkerOptions } from 'leaflet';

export function catalogPointStyle(inFarm: boolean, selected: boolean): CircleMarkerOptions {
  if (selected) {
    return {
      radius: 8,
      color: '#e4f8ff',
      weight: 2.5,
      fillColor: '#219ac3',
      fillOpacity: 1,
    };
  }
  return {
    radius: inFarm ? 7 : 5,
    color: inFarm ? '#bce783' : '#fff5c6',
    weight: inFarm ? 2.5 : 1.2,
    fillColor: inFarm ? '#8dba5b' : '#dfdb9d',
    fillOpacity: inFarm ? 0.9 : 0.7,
  };
}
