import { useSuspenseQuery } from '@tanstack/react-query';
import type { TableColumnsType } from 'antd';
import {
  Button,
  Card,
  Empty,
  Flex,
  Input,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Timeline,
  Typography,
} from 'antd';
import { History, Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { fieldQueries } from '../../../api/fields/fields.queries.ts';
import type { Field } from '../../../types/fields/field.types.ts';
import type { CropSeason, LandEventCategory } from '../../../types/fields/history.types.ts';

import { useLandHistoryFilters } from '../hooks/useLandHistoryFilters.ts';

const categoryColors: Record<LandEventCategory, string> = {
  'Crop rotation': 'success',
  'Soil conditions': 'warning',
  'Field work': 'default',
  'Weather & water': 'processing',
};

type LandHistoryProps = { field: Field };

export function LandHistory({ field }: LandHistoryProps) {
  const { t, i18n } = useTranslation();
  const rotationColumns: TableColumnsType<CropSeason> = [
    {
      title: t('Season'),
      dataIndex: 'year',
      render: (year: number) => (
        <Space>
          {year}
          {year === 2026 && <Tag color="success">{t('Current')}</Tag>}
        </Space>
      ),
    },
    { title: t('Crop'), dataIndex: 'crop' },
    { title: t('Planted'), dataIndex: 'planted' },
    { title: t('Harvested'), dataIndex: 'harvested' },
    { title: t('Yield'), dataIndex: 'yield' },
    {
      title: t('Soil after the season'),
      dataIndex: 'soilCondition',
      width: 270,
    },
  ];

  const { data: history } = useSuspenseQuery(fieldQueries.history(field.id));
  const events = history?.events ?? [];
  const seasons = history?.seasons ?? [];
  const { criteria, update, reset: resetFilters, visible } = useLandHistoryFilters(events);
  const { category, year, query } = criteria;

  return (
    <section aria-labelledby="land-history-heading" className="land-history-section">
      <Flex justify="space-between" align="center" gap={12} wrap>
        <Typography.Title level={3} id="land-history-heading">
          <History size={25} />
          {t('Land history')}{' '}
        </Typography.Title>
        <Tag>{t('{{value0}} records · 2023–2026', { value0: events.length })}</Tag>
      </Flex>
      <Typography.Paragraph type="secondary">
        {t(
          'Follow the story of this field: crop rotations, soil changes, field work, and weather through the seasons.',
        )}{' '}
      </Typography.Paragraph>
      <Card className="land-history-card">
        <Tabs
          defaultActiveKey="timeline"
          items={[
            {
              key: 'timeline',
              label: t('Activity timeline'),
              children: (
                <>
                  <Flex gap={12} wrap className="land-history-filters">
                    <Input
                      aria-label={t('Search land history')}
                      prefix={<Search size={18} />}
                      placeholder={t('Search field history…')}
                      value={query}
                      onChange={(event) => update({ query: event.target.value })}
                      allowClear
                    />
                    <Select
                      aria-label={t('Filter history by activity')}
                      value={category}
                      onChange={(category) => update({ category })}
                      options={['All activities', ...Object.keys(categoryColors)].map((value) => ({
                        value,
                        label: t(value),
                      }))}
                    />
                    <Select
                      aria-label={t('Filter history by year')}
                      value={year}
                      onChange={(year) => update({ year })}
                      options={['All years', '2026', '2025', '2024', '2023'].map((value) => ({
                        value,
                        label: t(value),
                      }))}
                    />
                    {(query || category !== 'All activities' || year !== 'All years') && (
                      <Button onClick={resetFilters}>{t('Clear filters')}</Button>
                    )}
                  </Flex>
                  <Flex justify="space-between" wrap gap={8} className="section-gap">
                    <Typography.Text type="secondary">
                      {t('Showing {{value0}} of {{value1}} records', {
                        value0: visible.length,
                        value1: events.length,
                      })}
                    </Typography.Text>
                    <Typography.Text type="secondary">
                      {t('Newest first · Scroll to explore earlier seasons')}
                    </Typography.Text>
                  </Flex>
                  <div
                    className="land-history-scroll"
                    role="region"
                    aria-label={t('{{value0}} activity timeline', { value0: field.name })}
                    tabIndex={0}
                  >
                    {visible.length > 0 && (
                      <Timeline
                        items={visible.map((event) => ({
                          key: event.id,
                          color: event.attention ? '#923a2e' : '#476b3c',
                          content: (
                            <article className="land-history-event">
                              <Typography.Text type="secondary" className="land-history-date">
                                {new Date(`${event.date}T12:00:00`).toLocaleDateString(
                                  i18n.resolvedLanguage,
                                  {
                                    month: 'long',
                                    day: 'numeric',
                                    year: 'numeric',
                                  },
                                )}
                              </Typography.Text>
                              <Space wrap>
                                <Typography.Title level={5}>{event.title}</Typography.Title>
                                <Tag color={categoryColors[event.category]}>{event.category}</Tag>
                                {event.attention && <Tag color="error">{t('Needs follow-up')}</Tag>}
                              </Space>
                              <Typography.Paragraph>{event.description}</Typography.Paragraph>
                              {event.measurements && (
                                <Flex gap={8} wrap>
                                  {event.measurements.map((measurement) => (
                                    <Tag key={measurement}>{measurement}</Tag>
                                  ))}
                                </Flex>
                              )}
                            </article>
                          ),
                        }))}
                      />
                    )}
                    {!visible.length && (
                      <Empty description={t('No history matches these filters.')}>
                        <Button onClick={resetFilters}>{t('Clear filters')}</Button>
                      </Empty>
                    )}
                  </div>
                </>
              ),
            },
            {
              key: 'rotations',
              label: t('Crop rotations'),
              children: (
                <Table<CropSeason>
                  rowKey="year"
                  columns={rotationColumns}
                  dataSource={seasons}
                  pagination={false}
                  scroll={{ x: 1150 }}
                />
              ),
            },
          ]}
        />
      </Card>
    </section>
  );
}
