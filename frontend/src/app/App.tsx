import { QueryClientProvider } from '@tanstack/react-query';
import { App as AntApp, ConfigProvider } from 'antd';
import enUS from 'antd/locale/en_US';
import ukUA from 'antd/locale/uk_UA';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { RouterProvider } from 'react-router-dom';
import { createQueryClient } from '../api/core/query-client.ts';
import { router } from './router.ts';
import { theme } from './theme.ts';

export default function App() {
  const [queryClient] = useState(createQueryClient);
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage === 'uk' ? ukUA : enUS;
  const componentLocale = {
    ...locale,
    Pagination: { ...locale.Pagination, page_size: t('Page size') },
  };

  return (
    <ConfigProvider theme={theme} locale={componentLocale}>
      <AntApp>
        <QueryClientProvider client={queryClient}>
          <RouterProvider router={router} />
        </QueryClientProvider>
      </AntApp>
    </ConfigProvider>
  );
}
