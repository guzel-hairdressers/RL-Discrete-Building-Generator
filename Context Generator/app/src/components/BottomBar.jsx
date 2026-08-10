import React from 'react';
import { useStore } from '../store/useStore';

export const BottomBar = () => {
  const filteredSites = useStore((s) => s.filteredSites);
  const activeSiteIndex = useStore((s) => s.activeSiteIndex);
  const pickRandomSite = useStore((s) => s.pickRandomSite);

  const total = filteredSites.length;
  const currentNum = total > 0 ? activeSiteIndex + 1 : 0;

  return (
    <div id="bottom-bar" className="glass-bottom-pill">
      <span id="match-counter-text">
        Site {currentNum} of {total}
      </span>
      <span className="pill-divider">|</span>
      <button className="btn-text-action" onClick={pickRandomSite}>
        Random Site
      </button>
    </div>
  );
};
