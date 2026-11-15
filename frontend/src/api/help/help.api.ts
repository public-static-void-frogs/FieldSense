import type { DataSource, TeamMember } from '../../types/help/help.types.ts';
import { request } from '../core/http.ts';

export const helpApi = {
  getTeam: (signal?: AbortSignal): Promise<TeamMember[]> => request('/help/team', { signal }),
  getSources: (signal?: AbortSignal): Promise<DataSource[]> => request('/help/sources', { signal }),
};
