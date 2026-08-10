import React, { useState, useEffect } from 'react';
import { useStore } from '../store/useStore';

export const BottomBar = () => {
  const filteredSites = useStore((s) => s.filteredSites);
  const activeSiteIndex = useStore((s) => s.activeSiteIndex);
  const setActiveSiteIndex = useStore((s) => s.setActiveSiteIndex);
  const pickRandomSite = useStore((s) => s.pickRandomSite);

  const total = filteredSites.length;
  const currentNum = total > 0 ? activeSiteIndex + 1 : 0;

  const [inputVal, setInputVal] = useState(String(currentNum));

  // Sync local input value whenever currentNum or total updates
  useEffect(() => {
    setInputVal(String(currentNum));
  }, [currentNum]);

  const commitValue = () => {
    const num = parseInt(inputVal, 10);
    if (!isNaN(num) && num >= 1 && num <= total) {
      setActiveSiteIndex(num - 1);
    } else {
      // Invalid input (out of bounds, empty, NaN): keep model unchanged and restore currentNum
      setInputVal(String(currentNum));
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      commitValue();
      e.target.blur();
    } else if (e.key === 'Escape') {
      setInputVal(String(currentNum));
      e.target.blur();
    }
  };

  return (
    <div id="bottom-bar" className="glass-bottom-pill">
      <div id="match-counter-text" style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
        <span>Site</span>
        <input
          type="text"
          className="site-number-input"
          value={inputVal}
          onChange={(e) => setInputVal(e.target.value)}
          onBlur={commitValue}
          onKeyDown={handleKeyDown}
          title="Type site number and press Enter to jump to site"
        />
        <span>of {total}</span>
      </div>
      <span className="pill-divider">|</span>
      <button className="btn-text-action" onClick={pickRandomSite}>
        Random Site
      </button>
    </div>
  );
};
