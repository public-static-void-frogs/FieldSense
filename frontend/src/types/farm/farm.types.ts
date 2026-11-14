export interface FarmProfile {
  language: 'en' | 'uk';
  sessionLifetimeHours: number;
  availableSeasons: string[];
  farmName: string;
  season: string;
  fullName: string;
  initials: string;
  email: string;
  role: string;
  location: string;
  latitude: number | null;
  longitude: number | null;
  locationLabel: string;
  timeZone: string;
  units: 'metric' | 'imperial';
  theme: 'light' | 'dark' | 'system';
}
