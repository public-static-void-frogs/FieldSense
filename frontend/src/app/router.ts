import { createBrowserRouter } from 'react-router-dom';
import { RouteLoading } from '../components/common/RouteLoading';
import { appRoutes } from './routes.ts';

export const router = createBrowserRouter(
  appRoutes.map((route) => ({ ...route, HydrateFallback: RouteLoading })),
);
