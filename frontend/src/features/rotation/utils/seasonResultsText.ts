import type { RotationSeasonResult } from '../../../types/rotation/rotation.types.ts';

export type SeasonCropNames = { id: string; names: string[] };

export type SeasonRowError = 'year' | 'crop' | 'yield' | 'duplicate';

export type ParsedSeasonRow = {
  line: number;
  text: string;
  result?: RotationSeasonResult;
  error?: SeasonRowError;
};

export const SEASON_YEAR_MIN = 1980;
export const SEASON_YEAR_MAX = 2100;
export const SEASON_YIELD_MAX = 1000;
export const SEASON_ROWS_MAX = 60;

const NUMBER = /^\d+(?:[.,]\d+)?$/;

function normalise(value: string): string {
  return value
    .toLowerCase()
    .replace(/\(.*?\)/g, ' ')
    .replace(/[^\p{L}]+/gu, ' ')
    .trim();
}

/** Cells of one pasted row: spreadsheet tabs, semicolons, commas or plain spaces. */
function cells(line: string): string[] {
  if (/[\t;]/.test(line)) {
    return line.split(/[\t;]/);
  }
  const commas = line.split(',').length - 1;
  // "2024 corn 70,5" is a decimal comma, not a column break.
  const decimalComma = commas === 1 && /\d,\d/.test(line) && /\s\S+\s/.test(line.trim());
  if (commas > 0 && !decimalComma) {
    return line.split(',');
  }

  return [line];
}

function matchCrop(text: string, crops: SeasonCropNames[]): string | undefined {
  const wanted = normalise(text);
  if (!wanted) {
    return undefined;
  }
  const named = crops.flatMap(({ id, names }) =>
    [id.replaceAll('_', ' '), ...names]
      .map(normalise)
      .filter(Boolean)
      .map((name) => ({ id, name })),
  );
  const same = (name: string) => name === wanted || name === `${wanted}s` || `${name}s` === wanted;
  const exact = named.find(({ name }) => same(name));
  if (exact) {
    return exact.id;
  }
  // Extra words such as a unit ("corn bu/ac"): take the longest crop name inside the text.
  const inside = named
    .filter(({ name }) => ` ${wanted} `.includes(` ${name} `))
    .sort((left, right) => right.name.length - left.name.length);

  return inside[0]?.id;
}

function parseRow(line: string, crops: SeasonCropNames[]): RotationSeasonResult | SeasonRowError {
  const tokens = cells(line)
    .flatMap((cell) => cell.trim().split(/\s+/))
    .filter(Boolean);
  const yearAt = tokens.findIndex((token) => /^\d{4}$/.test(token));
  const year = Number(tokens[yearAt]);
  if (yearAt < 0 || year < SEASON_YEAR_MIN || year > SEASON_YEAR_MAX) {
    return 'year';
  }
  const rest = tokens.filter((_, index) => index !== yearAt);
  const numbers = rest.filter((token) => NUMBER.test(token));
  const crop = matchCrop(rest.filter((token) => !NUMBER.test(token)).join(' '), crops);
  if (!crop) {
    return 'crop';
  }
  if (numbers.length === 0) {
    return { year, crop };
  }
  const yieldPerAcre = Number(numbers[0].replace(',', '.'));
  if (numbers.length > 1 || !(yieldPerAcre > 0) || yieldPerAcre > SEASON_YIELD_MAX) {
    return 'yield';
  }

  return { year, crop, yieldPerAcre };
}

/**
 * Pasted rows of "year, crop, yield per acre" in any column order, one season per line.
 * Lines without a digit (a header, a blank line) are skipped.
 */
export function parseSeasonResults(text: string, crops: SeasonCropNames[]): ParsedSeasonRow[] {
  const seen = new Set<number>();

  return text.split(/\r?\n/).flatMap((raw, index): ParsedSeasonRow[] => {
    const line = raw.trim();
    if (!/\d/.test(line)) {
      return [];
    }
    const parsed = parseRow(line, crops);
    if (typeof parsed === 'string') {
      return [{ line: index + 1, text: line, error: parsed }];
    }
    if (seen.has(parsed.year)) {
      return [{ line: index + 1, text: line, error: 'duplicate' }];
    }
    seen.add(parsed.year);

    return [{ line: index + 1, text: line, result: parsed }];
  });
}

export function validSeasonResults(rows: ParsedSeasonRow[]): RotationSeasonResult[] {
  return rows
    .flatMap(({ result }) => (result ? [result] : []))
    .sort((left, right) => left.year - right.year);
}

/** The stored results as text the parser reads back unchanged. */
export function formatSeasonResults(
  results: RotationSeasonResult[],
  label: (crop: string) => string,
): string {
  return [...results]
    .sort((left, right) => left.year - right.year)
    .map(({ year, crop, yieldPerAcre }) =>
      [year, label(crop), ...(yieldPerAcre ? [yieldPerAcre] : [])].join(', '),
    )
    .join('\n');
}
