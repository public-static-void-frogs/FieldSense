import { useQuery } from '@tanstack/react-query';
import { authQueries } from '../../../api/auth/auth.queries.ts';
import { RouteLoading } from '../../../components/common/RouteLoading.tsx';
import { AppLayout } from '../../layout/components/AppLayout.tsx';

export function AuthenticatedLayout() {
  const session = useQuery(authQueries.me());

  if (session.error) {
    throw session.error;
  }
  if (session.isPending) {
    return <RouteLoading />;
  }

  return <AppLayout key={session.data.id} />;
}
