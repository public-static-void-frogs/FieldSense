import { useQuery } from '@tanstack/react-query';
import { Navigate, useLocation } from 'react-router-dom';
import { authQueries } from '../../../api/auth/auth.queries.ts';
import { RouteLoading } from '../../../components/common/RouteLoading.tsx';
import { AppLayout } from '../../layout/components/AppLayout.tsx';
import { isUnauthorized } from '../utils/auth.ts';

export function AuthenticatedLayout() {
  const { pathname, search } = useLocation();
  const session = useQuery(authQueries.me());

  if (isUnauthorized(session.error)) {
    return <Navigate to={`/login?next=${encodeURIComponent(pathname + search)}`} replace />;
  }
  if (session.error) {
    throw session.error;
  }
  if (session.isPending) {
    return <RouteLoading />;
  }

  return <AppLayout />;
}
