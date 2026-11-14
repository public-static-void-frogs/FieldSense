export interface User {
  id: string;
  fullName: string;
  email: string;
}

export interface UserSettings {
  farmName: string;
  location: string;
  latitude: number | null;
  longitude: number | null;
  season: string;
  timeZone: string;
  units: 'metric' | 'imperial';
  theme: 'light' | 'dark' | 'system';
  language: 'en' | 'uk';
  sessionLifetimeHours: number;
}
