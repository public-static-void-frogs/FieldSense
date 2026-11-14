import { useChartAnimation } from '../../../hooks/useChartAnimation.ts';

export function useStrategyReview() {
  const animate = useChartAnimation();
  function reviewEvents() {
    document
      .getElementById('strategy-calendar-proposals')
      ?.scrollIntoView({ behavior: animate ? 'smooth' : 'instant', block: 'start' });
  }
  return { animate, reviewEvents };
}
