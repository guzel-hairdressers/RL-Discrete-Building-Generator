import React from 'react';
import { useStore } from '../store/useStore';

export const ViewToggle = () => {
  const viewMode = useStore((s) => s.viewMode);
  const setViewMode = useStore((s) => s.setViewMode);
  const maximizedPane = useStore((s) => s.maximizedPane);
  const setMaximizedPane = useStore((s) => s.setMaximizedPane);
  const visualsEnabled = useStore((s) => s.visualsEnabled);
  const setVisualsEnabled = useStore((s) => s.setVisualsEnabled);
  const isMaximized = maximizedPane === 'left';

  return (
    <div className="view-mode-pill glass-card top-toolbar-group">
      <button
        type="button"
        className={`view-btn ${viewMode === 'axonometric' ? 'active' : ''}`}
        onClick={() => setViewMode('axonometric')}
      >
        Axonometric
      </button>
      <button
        type="button"
        className={`view-btn ${viewMode === 'perspective' ? 'active' : ''}`}
        onClick={() => setViewMode('perspective')}
      >
        Perspective
      </button>
      <span className="toolbar-divider"></span>
      <button
        type="button"
        className={`view-btn visuals-toggle-btn ${visualsEnabled ? 'active' : ''}`}
        onClick={() => setVisualsEnabled(!visualsEnabled)}
        title={visualsEnabled
          ? 'Disable 3D/2D visuals (headless) — faster generation, monitoring only'
          : 'Re-enable 3D/2D visuals — no page reload, no weight reload'}
      >
        {visualsEnabled ? (
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z"></path>
            <circle cx="12" cy="12" r="3"></circle>
          </svg>
        ) : (
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"></path>
            <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"></path>
            <path d="M14.12 14.12a3 3 0 1 1-4.24-4.24"></path>
            <line x1="1" y1="1" x2="23" y2="23"></line>
          </svg>
        )}
        <span>{visualsEnabled ? '3D On' : '3D Off'}</span>
      </button>
      <span className="toolbar-divider"></span>
      <button
        type="button"
        className="view-btn toolbar-expand-btn"
        onClick={() => setMaximizedPane(isMaximized ? null : 'left')}
        title={isMaximized ? 'Restore View' : 'Maximize 3D View'}
      >
        {isMaximized ? (
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="4 14 10 14 10 20"></polyline>
            <polyline points="20 10 14 10 14 4"></polyline>
            <line x1="14" y1="10" x2="21" y2="3"></line>
            <line x1="3" y1="21" x2="10" y2="14"></line>
          </svg>
        ) : (
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
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

export default ViewToggle;
