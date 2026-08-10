import React, { useEffect } from 'react';
import { useStore } from '../store/useStore';

export const CarouselNav = () => {
  const navigateCarousel = useStore((s) => s.navigateCarousel);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'ArrowLeft') navigateCarousel(-1);
      if (e.key === 'ArrowRight') navigateCarousel(1);
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [navigateCarousel]);

  return (
    <>
      <button
        className="carousel-arrow left-arrow"
        onClick={() => navigateCarousel(-1)}
        title="Previous Site (Left Arrow Key)"
      >
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="15 18 9 12 15 6"></polyline>
        </svg>
      </button>

      <button
        className="carousel-arrow right-arrow"
        onClick={() => navigateCarousel(1)}
        title="Next Site (Right Arrow Key)"
      >
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="9 18 15 12 9 6"></polyline>
        </svg>
      </button>
    </>
  );
};
