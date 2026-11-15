import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { fieldQueries } from '../../../api/fields/fields.queries.ts';
import { mapQueries } from '../../../api/maps/maps.queries.ts';
import { planningQueries } from '../../../api/planning/planning.queries.ts';
import { rotationQueries } from '../../../api/rotation/rotation.queries.ts';

export function useDemoPreload(enabled: boolean) {
  const client = useQueryClient();
  const { data: fields } = useQuery({ ...fieldQueries.list(), enabled });

  useEffect(() => {
    if (enabled) {
      void client.prefetchQuery(mapQueries.summary());
      void client.prefetchQuery(planningQueries.events());
    }
  }, [client, enabled]);

  useEffect(() => {
    const field = fields?.[0];
    if (enabled && field) {
      void client.prefetchQuery(fieldQueries.byId(field.id));
      void client.prefetchQuery(fieldQueries.properties(field.id));
      void client.prefetchQuery(planningQueries.strategy(field.id));
      void client.prefetchQuery(rotationQueries.advice({ fieldId: field.id, priorities: [] }));
    }
  }, [client, enabled, fields]);
}
