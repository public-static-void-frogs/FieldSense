import { useEffect, useRef, useState } from 'react';
import { useChartAnimation } from './useChartAnimation.ts';

export function useChartVisibility() {
  const container = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const animate = useChartAnimation();
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: '0px 0px 40px 0px' },
    );
    if (container.current) {
      observer.observe(container.current);
    }
    return () => observer.disconnect();
  }, []);

  return { container, visible, animate };
}
