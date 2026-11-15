import { useQuery } from '@tanstack/react-query';
import { authQueries } from '../../../api/auth/auth.queries.ts';

export function useDemoMode() {
  return useQuery(authQueries.me()).data?.isDemo === true;
}
