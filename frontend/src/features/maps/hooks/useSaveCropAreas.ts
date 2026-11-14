import { useMutation, useQueryClient } from '@tanstack/react-query';
import { fieldMutations } from '../../../api/fields/fields.mutations.ts';
import type { CropZone } from '../../../types/maps/map.types.ts';

export function useSaveCropAreas(zones: CropZone[], onSaved: () => void) {
  const client = useQueryClient();
  const mutation = useMutation(fieldMutations.saveCropAreas(client));

  function save() {
    if (!zones.length || mutation.isPending) {
      return;
    }
    mutation.mutate(
      zones.map(({ crop, geometry }) => ({ crop, geometry })),
      {
        onSuccess: onSaved,
      },
    );
  }

  return { save, saving: mutation.isPending, saveError: mutation.isError };
}
