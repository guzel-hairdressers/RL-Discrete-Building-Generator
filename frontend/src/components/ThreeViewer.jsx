import React, { useEffect, useRef, useState, useCallback } from 'react';
import * as THREE from 'three';
import { useStore } from '../store/useStore';
import { SiteInfoCard } from './SiteInfoCard';
import { ViewToggle } from './ViewToggle';

export const ThreeViewer = () => {
  const activeIframeRef = useRef(null);
  const incomingIframeRef = useRef(null);

  const filteredSites = useStore((s) => s.filteredSites);
  const activeSiteIndex = useStore((s) => s.activeSiteIndex);
  const viewMode = useStore((s) => s.viewMode);
  const setViewMode = useStore((s) => s.setViewMode);
  const settings = useStore((s) => s.settings);
  const boundaries = useStore((s) => s.boundaries);
  const completed3DPlacements = useStore((s) => s.completed3DPlacements);
  const individualPlacementsList = useStore((s) => s.individualPlacementsList);
  const currentMergedPlacements = useStore((s) => s.currentMergedPlacements);
  const disableMerging = useStore((s) => s.disableMerging);
  const phase = useStore((s) => s.phase);
  const maximizedPane = useStore((s) => s.maximizedPane);

  const targetSite = filteredSites[activeSiteIndex];

  // Double-buffering state: active visible site vs incoming background loading site
  const [activeSite, setActiveSite] = useState(targetSite || null);
  const [incomingSite, setIncomingSite] = useState(null);

  // When targetSite changes, queue it as incomingSite
  useEffect(() => {
    if (!targetSite) {
      setActiveSite(null);
      setIncomingSite(null);
      return;
    }
    if (!activeSite) {
      setActiveSite(targetSite);
      setIncomingSite(null);
      return;
    }
    if (targetSite.site_id !== activeSite.site_id) {
      setIncomingSite(targetSite);
    } else {
      setIncomingSite(null);
    }
  }, [targetSite?.site_id]);

  const getTargetSrc = (s) => {
    if (!s) return null;
    const base = s.render_html
      ? s.render_html.startsWith('/') ? s.render_html : '/' + s.render_html
      : `/sites/${s.site_id}.html`;
    return `${base}?v=v0.9.0-alpha`;
  };

  const configureIframe = useCallback((iframe) => {
    if (!iframe || !iframe.contentWindow) return;

    // When paused, show intermediate merged placements; otherwise show completed episode building
    const effectiveList = (phase === 'paused' && !disableMerging && currentMergedPlacements && currentMergedPlacements.length > 0)
      ? currentMergedPlacements
      : ((completed3DPlacements && completed3DPlacements.length > 0)
          ? completed3DPlacements
          : ((!disableMerging && currentMergedPlacements && currentMergedPlacements.length > 0)
              ? currentMergedPlacements
              : []));

    const isReal = settings.boundaryType === 'real';
    const firstBoundary = Array.isArray(boundaries) && boundaries.length > 0 ? boundaries[0] : null;
    const currentBoundaryPoly = (!isReal && firstBoundary)
      ? (firstBoundary.outer || firstBoundary.polygon || firstBoundary.coords || null)
      : null;
    const boundaryOffset = firstBoundary ? {
      dx: Number(firstBoundary?.offset?.x || 0),
      dy: Number(firstBoundary?.offset?.y || 0),
      ox: Number(firstBoundary?.originOffset?.x || 0),
      oy: Number(firstBoundary?.originOffset?.y || 0),
    } : null;

    iframe.contentWindow.postMessage({
      type: 'set_context_visibility',
      visible: isReal,
      customPolygon: currentBoundaryPoly,
      boundaryOffset: boundaryOffset,
    }, '*');

    iframe.contentWindow.postMessage({
      type: 'optimizer_placements',
      placements: effectiveList,
      boundaries: boundaries,
      isReal: isReal,
      colorTheme: {
        core: '#ffcccc',
        coreShadow: '#ff9999',
        room: '#ffffff',
        roomShadow: '#e2e8f0',
        corridor: '#ffffff',
        corridorShadow: '#e2e8f0',
        special: '#ffffff',
        specialShadow: '#e2e8f0',
        edge: '#000000',
      },
    }, '*');

    try {
      const doc = iframe.contentDocument || iframe.contentWindow.document;
      // 1. Inject override style to permanently hide internal site UI elements
      const hideStyle = doc.createElement('style');
      hideStyle.innerHTML = '#controls-bar, #ui-container, .camera-toggle { display: none !important; visibility: hidden !important; }';
      doc.head.appendChild(hideStyle);

      // 2. Position Orientation Gizmo clearly visible in top-right of the 3D pane (no fly-in animation on reload)
      const gizmo = doc.getElementById('gizmo-container');
      if (gizmo) {
        gizmo.style.display = 'block';
        gizmo.style.visibility = 'visible';
        gizmo.style.opacity = '1';
        gizmo.style.top = '58px';
        gizmo.style.transition = 'none';
        gizmo.style.right = maximizedPane === 'left' ? '18px' : 'calc(25vw + 18px)';
        gizmo.style.zIndex = '100';
      }

      // 3. Enforce viewMode on the 3D scene
      const btnPersp = doc.getElementById('btn-persp');
      const btnOrtho = doc.getElementById('btn-ortho') || doc.getElementById('btn-axono');
      if (viewMode === 'axonometric' && btnOrtho) {
        btnOrtho.click();
      } else if (viewMode === 'perspective' && btnPersp) {
        btnPersp.click();
      }
      iframe.contentWindow.postMessage({ type: 'set_camera_mode', mode: viewMode }, '*');

      // 4. Hide surrounding context if boundary is not OSM Plot
      if (!isReal && doc.defaultView) {
        const win = doc.defaultView;
        if (win.scene) {
          win.scene.traverse((obj) => {
            if (obj.name && (obj.name.toLowerCase().includes('context') || obj.name.toLowerCase().includes('surround'))) {
              obj.visible = false;
            }
          });
        }
      }
    } catch (e) {}
  }, [completed3DPlacements, boundaries, currentMergedPlacements, individualPlacementsList, disableMerging, settings.boundaryType, viewMode, maximizedPane]);

  // Sync Gizmo Position on Pane Maximize / Restore (smooth transition on user toggle)
  useEffect(() => {
    const iframe = activeIframeRef.current;
    if (!iframe || !iframe.contentWindow) return;
    try {
      const doc = iframe.contentDocument || iframe.contentWindow.document;
      const gizmo = doc.getElementById('gizmo-container');
      if (gizmo) {
        gizmo.style.transition = 'right 0.5s cubic-bezier(0.16, 1, 0.3, 1)';
        gizmo.style.right = maximizedPane === 'left' ? '18px' : 'calc(25vw + 18px)';
      }
    } catch (e) {}
  }, [maximizedPane]);

  // Sync Camera Mode (Axo vs Persp) with the active 3D Engine
  useEffect(() => {
    const iframe = activeIframeRef.current;
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
      iframe.contentWindow.postMessage({ type: 'set_camera_mode', mode: viewMode }, '*');
    } catch (e) {}
  }, [viewMode, activeSite?.site_id]);

  // Listen to camera mode changes or viewer ready signals initiated inside the iframe
  useEffect(() => {
    const handleMsg = (e) => {
      if (e.data && e.data.type === 'camera_mode_change' && e.data.mode) {
        setViewMode(e.data.mode);
      }
      if (e.data && e.data.type === 'viewer_ready') {
        configureIframe(activeIframeRef.current);
      }
    };
    window.addEventListener('message', handleMsg);
    return () => window.removeEventListener('message', handleMsg);
  }, [setViewMode, configureIframe]);

  // Sync 3D Building Extrusions from Optimizer into the Active Scene
  useEffect(() => {
    configureIframe(activeIframeRef.current);
  }, [completed3DPlacements, currentMergedPlacements, individualPlacementsList, disableMerging, phase, boundaries, activeSite?.site_id, settings.boundaryType, configureIframe]);

  const handleActiveIframeLoad = () => {
    configureIframe(activeIframeRef.current);
  };

  const handleIncomingIframeLoad = () => {
    const nextIframe = incomingIframeRef.current;
    configureIframe(nextIframe);

    // After 80ms buffer paint, cleanly promote incoming site to active site (zero flicker!)
    setTimeout(() => {
      if (incomingSite) {
        setActiveSite(incomingSite);
        setIncomingSite(null);
      }
    }, 80);
  };

  const isMaximized = maximizedPane === 'left';
  const activeSrc = getTargetSrc(activeSite);
  const incomingSrc = getTargetSrc(incomingSite);

  return (
    <div className={`left-3d-pane ${isMaximized ? 'pane-maximized' : ''}`}>
      {/* 1. Visible Active Iframe */}
      {activeSrc && (
        <iframe
          ref={activeIframeRef}
          key={activeSite?.site_id}
          src={activeSrc}
          title={activeSite?.site_id || 'site'}
          onLoad={handleActiveIframeLoad}
          className="three-viewport-iframe"
          style={{
            zIndex: 1,
            pointerEvents: incomingSite ? 'none' : 'auto',
          }}
        />
      )}

      {/* 2. Seamless Incoming Buffer Iframe (zero flicker transition) */}
      {incomingSite && incomingSrc && (
        <iframe
          ref={incomingIframeRef}
          key={incomingSite.site_id}
          src={incomingSrc}
          title={incomingSite.site_id}
          onLoad={handleIncomingIframeLoad}
          className="three-viewport-iframe"
          style={{
            zIndex: 2,
            opacity: 0,
            pointerEvents: 'none',
          }}
        />
      )}

      {!activeSite && !incomingSite && (
        <div className="empty-scene" style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div className="empty-msg" style={{ color: '#64748b', fontWeight: 600 }}>No sites match the selected filters</div>
        </div>
      )}

      {/* Floating UI Elements matching wireframe sketch */}
      <SiteInfoCard />
      {/* Upper View Toggle & Integrated Expand Toolbar */}
      <ViewToggle />
    </div>
  );
};

export default ThreeViewer;
