import type { AppRouteHandle } from '../../../app/routes.ts';

export function getWorkspaceClassName(workspace: AppRouteHandle['workspace']) {
  if (workspace === 'map' || workspace === 'calendar') {
    return 'main-content main-content-map';
  }
  return 'main-content';
}
