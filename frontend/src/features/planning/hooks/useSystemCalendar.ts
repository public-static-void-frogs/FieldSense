import type { CalendarProps } from 'antd';
import { Grid } from 'antd';
import type { Dayjs } from 'dayjs';

type UseSystemCalendarOptions = {
  onDateSelect: (date: string) => void;
  onPanelDateChange: (date: string) => void;
  onModeChange: (mode: NonNullable<CalendarProps<Dayjs>['mode']>) => void;
};

export function useSystemCalendar({
  onDateSelect,
  onModeChange,
  onPanelDateChange,
}: UseSystemCalendarOptions) {
  const screens = Grid.useBreakpoint();
  const selectDate: CalendarProps<Dayjs>['onSelect'] = (date, info) => {
    if (info.source === 'date') {
      onDateSelect(date.format('YYYY-MM-DD'));
    }
    if (info.source === 'month') {
      onModeChange('month');
      onPanelDateChange(date.format('YYYY-MM-DD'));
    }
  };
  const changePanel: CalendarProps<Dayjs>['onPanelChange'] = (date, mode) => {
    onModeChange(mode);
    onPanelDateChange(date.format('YYYY-MM-DD'));
  };
  return { compact: screens.md === false, selectDate, changePanel };
}
