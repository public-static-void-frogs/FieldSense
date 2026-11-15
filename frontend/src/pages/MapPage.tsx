import { Navigate, useLocation } from 'react-router-dom';
import { useDemoMode } from '../features/demo/hooks/useDemoMode.ts';
import { CatalogMap } from '../features/maps/components/CatalogMap';

export function MapPage() {
  const demo = useDemoMode();
  const { pathname, search } = useLocation();

  return demo && pathname === '/map/add' ? (
    <Navigate to={`/map${search}`} replace />
  ) : (
    <CatalogMap />
  );
}
