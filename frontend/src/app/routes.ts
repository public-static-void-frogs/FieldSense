import type { RouteObject } from 'react-router-dom';
import { calendarLoader, fieldLoader } from './route-loaders.ts';

export type AppRouteHandle = {
  navigationKey?: string;
  workspace?: 'map' | 'calendar';
  preserveScroll?: boolean;
};

export const appRoutes: RouteObject[] = [
  {
    id: 'root',
    lazy: async () => ({
      Component: (await import('./RootLayout')).RootLayout,
      ErrorBoundary: (await import('../pages/RouteErrorPage')).RouteErrorPage,
    }),
    children: [
      {
        id: 'about',
        path: 'about',
        lazy: async () => ({ Component: (await import('../pages/AboutPage')).AboutPage }),
      },
      {
        id: 'privacy',
        path: 'privacy',
        lazy: async () => ({ Component: (await import('../pages/PrivacyPage')).PrivacyPage }),
      },
      {
        id: 'terms',
        path: 'terms',
        lazy: async () => ({ Component: (await import('../pages/TermsPage')).TermsPage }),
      },
      {
        id: 'support',
        path: 'support',
        lazy: async () => ({ Component: (await import('../pages/SupportPage')).SupportPage }),
      },
      {
        id: 'login',
        path: 'login',
        lazy: async () => ({ Component: (await import('../pages/LoginPage')).LoginPage }),
      },
      {
        id: 'register',
        path: 'register',
        lazy: async () => ({ Component: (await import('../pages/RegisterPage')).RegisterPage }),
      },
      {
        id: 'farm',
        lazy: async () => ({
          Component: (await import('../features/auth/components/AuthenticatedLayout'))
            .AuthenticatedLayout,
        }),
        children: [
          {
            id: 'overview',
            index: true,
            handle: { navigationKey: '/' },
            lazy: async () => ({ Component: (await import('../pages/OverviewPage')).OverviewPage }),
          },
          {
            id: 'fields',
            path: 'fields',
            handle: { navigationKey: '/fields' },
            lazy: async () => ({ Component: (await import('../pages/FieldsPage')).FieldsPage }),
          },
          {
            id: 'field',
            path: 'fields/:fieldId',
            loader: fieldLoader,
            handle: { navigationKey: '/fields' },
            lazy: async () => ({
              Component: (await import('../pages/FieldDetailsPage')).FieldDetailsPage,
            }),
          },
          {
            id: 'strategy',
            path: 'fields/:fieldId/strategy',
            loader: fieldLoader,
            handle: { navigationKey: '/fields' },
            lazy: async () => ({
              Component: (await import('../pages/FieldStrategyPage')).FieldStrategyPage,
            }),
          },
          {
            id: 'map',
            path: 'map',
            handle: { navigationKey: '/map', workspace: 'map' },
            lazy: async () => ({ Component: (await import('../pages/MapPage')).MapPage }),
          },
          {
            id: 'map-add',
            path: 'map/add',
            handle: { navigationKey: '/map', workspace: 'map' },
            lazy: async () => ({ Component: (await import('../pages/MapPage')).MapPage }),
          },
          {
            id: 'catalog-field',
            path: 'map/add/:fieldId',
            loader: fieldLoader,
            handle: { navigationKey: '/map' },
            lazy: async () => ({ Component: (await import('../pages/AddFieldPage')).AddFieldPage }),
          },
          {
            id: 'calendar',
            path: 'calendar/:date?',
            loader: calendarLoader,
            handle: { navigationKey: '/calendar', workspace: 'calendar', preserveScroll: true },
            lazy: async () => ({ Component: (await import('../pages/CalendarPage')).CalendarPage }),
          },
          {
            id: 'action',
            path: 'calendar/actions/:eventId',
            handle: { navigationKey: '/calendar' },
            lazy: async () => ({
              Component: (await import('../pages/ActionDetailsPage')).ActionDetailsPage,
            }),
          },
          {
            id: 'history',
            path: 'history',
            handle: { navigationKey: '/history' },
            lazy: async () => ({ Component: (await import('../pages/HistoryPage')).HistoryPage }),
          },
          {
            id: 'settings',
            path: 'settings',
            handle: { navigationKey: '/settings' },
            lazy: async () => ({ Component: (await import('../pages/SettingsPage')).SettingsPage }),
          },
          {
            id: 'help',
            path: 'help',
            handle: { navigationKey: '/help' },
            lazy: async () => ({ Component: (await import('../pages/HelpPage')).HelpPage }),
          },
          {
            id: 'notifications',
            path: 'notifications',
            handle: { navigationKey: '/notifications' },
            lazy: async () => ({
              Component: (await import('../pages/NotificationsPage')).NotificationsPage,
            }),
          },
          {
            id: 'not-found',
            path: '*',
            lazy: async () => ({
              Component: (await import('../pages/RouteErrorPage')).RouteErrorPage,
            }),
          },
        ],
      },
    ],
  },
];
