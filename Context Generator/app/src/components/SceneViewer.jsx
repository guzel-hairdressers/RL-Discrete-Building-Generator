import React, { useState, useEffect } from 'react';
import { useStore } from '../store/useStore';

export const SceneViewer = () => {
  const filteredSites = useStore((s) => s.filteredSites);
  const activeSiteIndex = useStore((s) => s.activeSiteIndex);

  const site = filteredSites[activeSiteIndex];

  // Resolve exact file path safely from site.render_html or site.site_id
  const currentSrc = site
    ? site.render_html
      ? site.render_html.startsWith('/') ? site.render_html : '/' + site.render_html
      : `/output/${site.site_id}.html`
    : null;

  const [activeBuffer, setActiveBuffer] = useState('A');
  const [srcA, setSrcA] = useState(currentSrc || '');
  const [srcB, setSrcB] = useState('');

  useEffect(() => {
    if (!currentSrc) return;

    if (activeBuffer === 'A') {
      if (srcA !== currentSrc) {
        setSrcB(currentSrc);
        setActiveBuffer('B');
      }
    } else {
      if (srcB !== currentSrc) {
        setSrcA(currentSrc);
        setActiveBuffer('A');
      }
    }
  }, [currentSrc]);

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
        key="buffer-a"
        src={srcA}
        title="Scene Buffer A"
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
          transition: 'opacity 0.1s ease-in-out',
        }}
      />

      {/* Buffer B */}
      <iframe
        key="buffer-b"
        src={srcB}
        title="Scene Buffer B"
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
          transition: 'opacity 0.1s ease-in-out',
        }}
      />
    </div>
  );
};
