import type { UserSettings } from '../../../types/auth/auth.types.ts';
import type { FarmProfile } from '../../../types/farm/farm.types.ts';

export type SettingsValues = UserSettings & { fullName: string; email: string };
export type SettingsSection = 'account' | 'preferences' | 'farm' | 'location';

export const sectionFields: Record<SettingsSection, (keyof SettingsValues)[]> = {
  account: ['fullName', 'email'],
  preferences: ['units', 'language', 'theme', 'sessionLifetimeHours'],
  farm: ['farmName', 'season', 'timeZone'],
  location: ['location', 'latitude', 'longitude'],
};

export function settingsFrom(profile: FarmProfile): UserSettings {
  return {
    farmName: profile.farmName,
    location: profile.location,
    latitude: profile.latitude,
    longitude: profile.longitude,
    season: profile.season,
    timeZone: profile.timeZone,
    units: profile.units,
    theme: profile.theme,
    language: profile.language,
    sessionLifetimeHours: profile.sessionLifetimeHours,
  };
}

export function formValuesFrom(profile: FarmProfile): SettingsValues {
  return { ...settingsFrom(profile), fullName: profile.fullName, email: profile.email };
}

export function isSectionDirty(
  section: SettingsSection,
  values: Partial<SettingsValues>,
  saved: SettingsValues,
): boolean {
  return sectionFields[section].some((key) => values[key] !== saved[key]);
}

export function settingsForSection(
  section: Exclude<SettingsSection, 'account'>,
  values: SettingsValues,
  profile: FarmProfile,
): UserSettings {
  const updated = settingsFrom(profile);
  for (const key of sectionFields[section]) {
    Object.assign(updated, { [key]: values[key] });
  }
  return updated;
}
