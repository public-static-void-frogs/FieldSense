export function insightNumber(
  value: number | null | undefined,
  locale: string,
  style: 'decimal' | 'percent' = 'decimal',
) {
  if (value == null) {
    return '—';
  }
  return new Intl.NumberFormat(locale, { style, maximumFractionDigits: 2 }).format(value);
}

export function insightDate(date: string | null | undefined, locale: string) {
  if (!date || !/^\d{2}-\d{2}$/.test(date)) {
    return '—';
  }
  const calendarDate = new Date(`2001-${date}T00:00:00Z`);
  if (!Number.isFinite(calendarDate.getTime())) {
    return '—';
  }
  return new Intl.DateTimeFormat(locale, {
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  }).format(calendarDate);
}

export function insightSigned(value: number | null | undefined, locale: string) {
  if (value == null) {
    return '—';
  }
  return new Intl.NumberFormat(locale, {
    maximumFractionDigits: 3,
    signDisplay: 'exceptZero',
  }).format(value);
}
