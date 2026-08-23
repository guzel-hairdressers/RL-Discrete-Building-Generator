import React, { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { useStore } from '../store/useStore';
import { SiteInfoCard } from './SiteInfoCard';
import { CarouselNav } from './CarouselNav';
import { ViewToggle } from './ViewToggle';

export const ThreeViewer = () => {
  const iframeRef = useRef(null);

  const filteredSites = useStore((s) => s.filteredSites);
  const activeSiteIndex = useStore((s) => s.activeSiteIndex);
  const viewMode = useStore((s) => s.viewMode);
  const boundaries = useStore((s) => s.boundaries);
  const completed3DPlacements = useStore((s) => s.completed3DPlacements);
  const individualPlacementsList = useStore((s) => s.individualPlacementsList);
  const currentMergedPlacements = useStore((s) => s.currentMergedPlacements);
  const disableMerging = useStore((s) => s.disableMerging);
  const maximizedPane = useStore((s) => s.maximizedPane);
  const setMaximizedPane = useStore((s) => s.setMaximizedPane);

  const site = filteredSites[activeSiteIndex];

  // Direct reference to the exact Context Generator standalone 3D visualization
  const targetSrc = site
    ? site.render_html
      ? site.render_html.startsWith('/') ? site.render_html : '/' + site.render_html
      : `/sites/${site.site_id}.html`
    : null;

  // Sync Camera Mode (Axo vs Persp) with the underlying 3D Engine in the iframe
  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe || !iframe.contentWindow) return;
    try {
      const doc = iframe.contentDocument || iframe.contentWindow.document;
      if (viewMode === 'axonometric') {
        const btn = doc.getElementById('btn-ortho') || doc.getElementById('btn-axono');
        if (btn) btn.click();
      } else {
        const btn = doc.getElementById('btn-persp');
        if (btn) btn.click();
      }
    } catch (e) {}
  }, [viewMode]);

  // Sync 3D Building Extrusions from Optimizer into the Scene
  // Only update when completed3DPlacements updates at the end of an episode!
  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe || !iframe.contentWindow) return;

    // Use completed3DPlacements if available; otherwise fallback to current if initial load
    const effectiveList = (completed3DPlacements && completed3DPlacements.length > 0)
      ? completed3DPlacements
      : ((!disableMerging && currentMergedPlacements.length > 0)
          ? currentMergedPlacements
          : individualPlacementsList);

    iframe.contentWindow.postMessage({
      type: 'optimizer_placements',
      placements: effectiveList,
      boundaries: boundaries,
    }, '*');
  }, [completed3DPlacements, boundaries, activeSiteIndex]);

  const handleIframeLoad = () => {
    const iframe = iframeRef.current;
    if (!iframe || !iframe.contentWindow) return;

    const effectiveList = (completed3DPlacements && completed3DPlacements.length > 0)
      ? completed3DPlacements
      : ((!disableMerging && currentMergedPlacements.length > 0)
          ? currentMergedPlacements
          : individualPlacementsList);

    iframe.contentWindow.postMessage({
      type: 'optimizer_placements',
      placements: effectiveList,
      boundaries: boundaries,
    }, '*');

    try {
      // Hide internal fallback UI cards since we render the rich React UI over the iframe
      const doc = iframe.contentDocument || iframe.contentWindow.document;
      const card = doc.getElementById('ui-container');
      if (card) card.style.display = 'none';
      const cBar = doc.getElementById('controls-bar');
      if (cBar) cBar.style.display = 'none';
    } catch (e) {}
  };

  const isMaximized = maximizedPane === 'left';

  return (
    <div className={`left-3d-pane ${isMaximized ? 'pane-maximized' : ''}`}>
      {targetSrc ? (
        <iframe
          ref={iframeRef}
          key={site?.site_id || 'site'}
          src={targetSrc}
          title={site?.site_id || 'site'}
          onLoad={handleIframeLoad}
          style={{
            width: '100%',
            height: '100%',
            border: 'none',
            display: 'block',
            background: '#ffffff',
          }}
        />
      ) : (
        <div className="empty-scene" style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div className="empty-msg" style={{ color: '#64748b', fontWeight: 600 }}>No sites match the selected filters</div>
        </div>
      )}

      {/* Floating UI Elements matching wireframe sketch */}
      <SiteInfoCard />
      <ViewToggle />
      <CarouselNav />

      {/* Split-View Expand / Collapse Button */}
      <button
        type="button"
        className="pane-expand-btn left-expand"
        onClick={() => setMaximizedPane('left')}
        title={isMaximized ? 'Restore Split View' : 'Expand 3D Context View (100%)'}
      >
        {isMaximized ? (
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="4 14 10 14 10 20"></polyline>
            <polyline points="20 10 14 10 14 4"></polyline>
            <line x1="14" y1="10" x2="21" y2="3"></line>
            <line x1="3" y1="21" x2="10" y2="14"></line>
          </svg>
        ) : (
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="15 3 21 3 21 9"></polyline>
            <polyline points="9 21 3 21 3 15"></polyline>
            <line x1="21" y1="3" x2="14" y2="10"></line>
            <line x1="3" y1="21" x2="10" y2="14"></line>
          </svg>
        )}
      </button>
    </div>
  );
};

export default ThreeViewer;
