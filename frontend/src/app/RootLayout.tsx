import { QueryErrorResetBoundary } from '@tanstack/react-query';
import { Suspense } from 'react';
import { Outlet, ScrollRestoration, useLocation, useMatches } from 'react-router-dom';
import { QueryBoundary } from '../components/common/QueryBoundary';
import { RouteLoading } from '../components/common/RouteLoading';
import type { AppRouteHandle } from './routes.ts';

export function RootLayout() {
  const { pathname } = useLocation();
  const matches = useMatches();
  const calendarView = matches.some(
    (match) => (match.handle as AppRouteHandle | undefined)?.preserveScroll,
  );

  return (
    <>
      <QueryErrorResetBoundary>
        {({ reset }) => (
          <QueryBoundary key={calendarView ? 'calendar' : pathname} onReset={reset}>
            <Suspense fallback={<RouteLoading />}>
              <Outlet />
            </Suspense>
          </QueryBoundary>
        )}
      </QueryErrorResetBoundary>
      <ScrollRestoration />
    </>
  );
}
