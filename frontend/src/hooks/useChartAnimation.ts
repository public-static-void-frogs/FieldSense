import { useEffect, useState } from 'react';

export function useChartAnimation() {
  const [animate, setAnimate] = useState(
    () => !window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  );
  useEffect(() => {
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setAnimate(!preference.matches);
    update();
    preference.addEventListener('change', update);
    return () => preference.removeEventListener('change', update);
  }, []);
  return animate;
}
