import { skipToken, useQuery, useQueryClient } from '@tanstack/react-query';
import { cropHistoryQueries } from '../../../api/fields/crop-history.queries.ts';
import { buildCropPatterns } from '../utils/cropPatterns.ts';

export function useCropPatterns(
  fieldId: string,
  part: number,
  geometryKey: string,
  years: number[],
) {
  const client = useQueryClient();

  return useQuery({
    queryKey: ['fields', fieldId, 'crop-history', geometryKey, part, 'patterns', years],
    queryFn: years.length
      ? async ({ signal }) => {
          const layers = await Promise.all(
            years.map(async (year) => ({
              year,
              layer: await client.fetchQuery(
                cropHistoryQueries.layer(fieldId, part, geometryKey, year),
              ),
            })),
          );
          signal.throwIfAborted();
          const patterns = buildCropPatterns(layers);
          if (!patterns) {
            return { bounds: layers[0].layer.bounds, image: null, patterns: null };
          }

          const canvas = document.createElement('canvas');
          canvas.width = patterns.width;
          canvas.height = patterns.height;
          const context = canvas.getContext('2d');
          if (!context) {
            throw new Error('Could not render crop patterns');
          }
          context.putImageData(
            new ImageData(patterns.colors, patterns.width, patterns.height),
            0,
            0,
          );

          return { bounds: patterns.bounds, image: canvas.toDataURL(), patterns };
        }
      : skipToken,
    staleTime: 60 * 60 * 1000,
    retry: false,
  });
}
