export const satelliteTiles = {
  url: 'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
  attribution:
    'Imagery &copy; <a href="https://www.esri.com/">Esri</a>, Maxar, Earthstar Geographics, and the GIS User Community',
};

export const detectedCropIcons: Record<string, string> = {
  'Winter wheat': '🌾',
  Corn: '🌽',
  Soybeans: '🫘',
  Alfalfa: '🌱',
  'Grassland/Pasture': '🌿',
};
export const detectedCropColors: Record<string, string> = {
  'Winter wheat': '#dcc67d',
  Corn: '#e8bd55',
  Soybeans: '#9fca7a',
  Alfalfa: '#c29ad8',
  'Grassland/Pasture': '#75cbb0',
};
