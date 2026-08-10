import React, { useState, useEffect, useRef } from 'react';
import { useStore } from '../store/useStore';

export const SceneViewer = () => {
  const filteredSites = useStore((s) => s.filteredSites);
  const activeSiteIndex = useStore((s) => s.activeSiteIndex);

  const site = filteredSites[activeSiteIndex];

  // Resolve exact file path safely from site.render_html or site.site_id
  const targetSrc = site
    ? site.render_html
      ? site.render_html.startsWith('/') ? site.render_html : '/' + site.render_html
      : `/output/${site.site_id}.html`
    : null;

  // Active buffer tracking ('A' or 'B')
  const [activeBuffer, setActiveBuffer] = useState('A');
  const [srcA, setSrcA] = useState(targetSrc || '');
  const [srcB, setSrcB] = useState('');

  // When targetSrc changes, load it into the hidden buffer
  useEffect(() => {
    if (!targetSrc) return;

    if (activeBuffer === 'A') {
      if (srcA !== targetSrc) {
        if (srcB === targetSrc) {
          setActiveBuffer('B');
        } else {
          setSrcB(targetSrc);
        }
      }
    } else {
      if (srcB !== targetSrc) {
        if (srcA === targetSrc) {
          setActiveBuffer('A');
        } else {
          setSrcA(targetSrc);
        }
      }
    }
  }, [targetSrc, activeBuffer, srcA, srcB]);

  // When hidden iframe finishes loading, cross-fade to it!
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

  if (!site || !targetSrc) {
    return (
      <div id="canvas-container" className="empty-scene">
        <div className="empty-msg">No sites match the selected filters</div>
      </div>
    );
  }

  return (
    <div
      id="canvas-container"
      style={{
        width: '100vw',
        height: '100vh',
        position: 'absolute',
        top: 0,
        left: 0,
        background: '#f8fafc',
        overflow: 'hidden',
      }}
    >
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
          background: '#f8fafc',
          opacity: activeBuffer === 'A' ? 1 : 0,
          zIndex: activeBuffer === 'A' ? 2 : 1,
          pointerEvents: activeBuffer === 'A' ? 'auto' : 'none',
          transition: 'opacity 0.15s ease-in-out',
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
          background: '#f8fafc',
          opacity: activeBuffer === 'B' ? 1 : 0,
          zIndex: activeBuffer === 'B' ? 2 : 1,
          pointerEvents: activeBuffer === 'B' ? 'auto' : 'none',
          transition: 'opacity 0.15s ease-in-out',
        }}
      />
    </div>
  );
};
