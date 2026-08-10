import React from 'react';
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

  if (!site || !currentSrc) {
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
      }}
    >
      <iframe
        key={currentSrc}
        src={currentSrc}
        title="3D Context Scene"
        style={{
          width: '100%',
          height: '100%',
          border: 'none',
          background: '#f8fafc',
        }}
      />
    </div>
  );
};
