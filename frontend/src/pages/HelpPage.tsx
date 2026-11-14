import { ProductNotice } from '../features/legal/components/ProductNotice.tsx';
import { useSuspenseQuery } from '@tanstack/react-query';
import { Card, Collapse, Table, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { helpQueries } from '../api/help/help.queries.ts';
import { ProjectSection } from '../features/help/components/ProjectSection';
import { TeamSection } from '../features/help/components/TeamSection';

export function HelpPage() {
  const { t } = useTranslation();
  const { data: demoSources } = useSuspenseQuery(helpQueries.sources());

  return (
    <>
      <ProductNotice />
      <div className="help-about-sections">
        <ProjectSection />
        <TeamSection />
      </div>
      <div className="help-reference-sections">
        <section aria-label={t('Q&A')}>
          <Card title={t('Q&A')}>
            <Collapse
              defaultActiveKey={['fields']}
              items={[
                {
                  key: 'fields',
                  label: t('How do I open a field?'),
                  children: t(
                    'Open My fields and click a field name to see its location, crop and soil properties, recommendations, and rotation strategy.',
                  ),
                },
                {
                  key: 'add',
                  label: t('How do I select fields on the map?'),
                  children: t(
                    'Use the hand button to move the map. Draw a zone with the lasso, then click Add to open its preview panel. Cancel section removes the zone and restores its points. This does not change My fields.',
                  ),
                },
                {
                  key: 'warnings',
                  label: t('What do the health indicators mean?'),
                  children: t(
                    'Green means healthy. Amber means a field needs attention. Red marks a critical metric that calls for prompt care. Each indicator includes a plain-language explanation.',
                  ),
                },
                {
                  key: 'history',
                  label: t('Where can I find weather history?'),
                  children: t(
                    'Open Environment to explore the 14-day forecast, recent weather, or a custom historical date range for your saved location.',
                  ),
                },
                {
                  key: 'remove',
                  label: t('How do I remove a field?'),
                  children: t(
                    'Open a field’s page and use Remove field in the management card. Confirm inline to remove it. Its parcel stays available to add again from the map.',
                  ),
                },
              ]}
            />
          </Card>
        </section>
        <section aria-label={t('Data sources')}>
          <Card title={t('Data sources')}>
            <Typography.Paragraph type="secondary">
              {t(
                'Example sources for the demo. These datasets are placeholders and are not connected.',
              )}
            </Typography.Paragraph>
            <Table
              rowKey="key"
              dataSource={demoSources}
              pagination={false}
              scroll={{ x: 620 }}
              columns={[
                { title: t('Source'), dataIndex: 'name', width: 240 },
                { title: t('Data included'), dataIndex: 'data' },
                { title: t('Format'), dataIndex: 'format', width: 110 },
              ]}
            />
          </Card>
        </section>
      </div>
    </>
  );
}
