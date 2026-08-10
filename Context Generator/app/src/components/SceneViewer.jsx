import React from 'react';
import { useStore } from '../store/useStore';

export const SceneViewer = () => {
  const filteredSites = useStore((s) => s.filteredSites);
  const activeSiteIndex = useStore((s) => s.activeSiteIndex);

  const site = filteredSites[activeSiteIndex];

  if (!site) {
    return (
      <div id="canvas-container" className="empty-scene" style={{ width: '100vw', height: '100vh' }}>
        <div className="empty-msg">No sites match the selected filters</div>
      </div>
    );
  }

  const iframeSrc = `/output/${site.site_id}.html`;

  return (
    <div id="canvas-container" style={{ width: '100vw', height: '100vh', position: 'absolute', top: 0, left: 0 }}>
      <iframe
        key={site.site_id}
        src={iframeSrc}
        title={site.site_id}
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100vw',
          height: '100vh',
          border: 'none',
          zIndex: 1,
        }}
      />
    </div>
  );
};
