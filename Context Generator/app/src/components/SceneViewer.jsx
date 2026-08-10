import React from 'react';
import { useStore } from '../store/useStore';

export const SceneViewer = () => {
  const filteredSites = useStore((s) => s.filteredSites);
  const activeSiteIndex = useStore((s) => s.activeSiteIndex);

  const site = filteredSites[activeSiteIndex];

  if (!site) {
    return (
      <div id="canvas-container" className="empty-scene">
        <div className="empty-msg">No sites match the selected filters</div>
      </div>
    );
  }

  const iframeSrc = `/output/${site.site_id}.html`;

  return (
    <div id="canvas-container">
      <iframe
        key={site.site_id}
        src={iframeSrc}
        title={site.site_id}
        className="scene-iframe"
        style={{
          width: '100%',
          height: '100%',
          border: 'none',
        }}
      />
    </div>
  );
};
