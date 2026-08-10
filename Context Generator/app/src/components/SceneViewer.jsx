import React, { useState, useEffect, useRef } from 'react';
import { useStore } from '../store/useStore';

export const SceneViewer = () => {
  const filteredSites = useStore((s) => s.filteredSites);
  const activeSiteIndex = useStore((s) => s.activeSiteIndex);

  const site = filteredSites[activeSiteIndex];
  const targetId = site ? site.site_id : null;

  // Active buffer tracking ('A' or 'B')
  const [activeBuffer, setActiveBuffer] = useState('A');
  const [srcA, setSrcA] = useState('');
  const [srcB, setSrcB] = useState('');

  const targetIdRef = useRef(targetId);
  targetIdRef.current = targetId;

  // Preload and switch buffers when site changes
  useEffect(() => {
    if (!targetId) return;

    const newSrc = `/output/${targetId}.html`;

    // First load
    if (!srcA && !srcB) {
      setSrcA(newSrc);
      setActiveBuffer('A');
      return;
    }

    if (activeBuffer === 'A') {
      if (srcA === newSrc) return;
      setSrcB(newSrc);
    } else {
      if (srcB === newSrc) return;
      setSrcA(newSrc);
    }
  }, [targetId]);

  const handleLoadA = () => {
    if (srcA && activeBuffer !== 'A') {
      setActiveBuffer('A');
    }
  };

  const handleLoadB = () => {
    if (srcB && activeBuffer !== 'B') {
      setActiveBuffer('B');
    }
  };

  if (!site) {
    return (
      <div id="canvas-container" className="empty-scene">
        <div className="empty-msg">No sites match the selected filters</div>
      </div>
    );
  }

  return (
    <div id="canvas-container" style={{ width: '100vw', height: '100vh', position: 'absolute', top: 0, left: 0 }}>
      {/* Buffer A */}
      <iframe
        src={srcA}
        title="Scene Buffer A"
        onLoad={handleLoadA}
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100vw',
          height: '100vh',
          border: 'none',
          opacity: activeBuffer === 'A' ? 1 : 0,
          zIndex: activeBuffer === 'A' ? 2 : 1,
          pointerEvents: activeBuffer === 'A' ? 'auto' : 'none',
          transition: 'opacity 0.12s ease-in-out',
        }}
      />

      {/* Buffer B */}
      <iframe
        src={srcB}
        title="Scene Buffer B"
        onLoad={handleLoadB}
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100vw',
          height: '100vh',
          border: 'none',
          opacity: activeBuffer === 'B' ? 1 : 0,
          zIndex: activeBuffer === 'B' ? 2 : 1,
          pointerEvents: activeBuffer === 'B' ? 'auto' : 'none',
          transition: 'opacity 0.12s ease-in-out',
        }}
      />
    </div>
  );
};
