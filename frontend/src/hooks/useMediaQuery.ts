import { useEffect, useState } from 'react';
import { MEDIA_QUERIES } from '../theme/tokens';

export const matchesMedia = (query: string): boolean => (
  typeof window !== 'undefined'
  && typeof window.matchMedia === 'function'
  && window.matchMedia(query).matches
);

export const isMobileViewport = (): boolean => matchesMedia(MEDIA_QUERIES.belowMd);

export const useMediaQuery = (query: string): boolean => {
  const [matches, setMatches] = useState(() => matchesMedia(query));

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return;
    }

    const mediaQuery = window.matchMedia(query);
    const handleChange = (event: MediaQueryListEvent) => setMatches(event.matches);
    setMatches(mediaQuery.matches);
    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, [query]);

  return matches;
};

export const useIsMobile = (): boolean => useMediaQuery(MEDIA_QUERIES.belowMd);
