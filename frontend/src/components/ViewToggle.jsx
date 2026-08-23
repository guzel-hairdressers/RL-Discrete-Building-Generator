import React from 'react';
import { useStore } from '../store/useStore';

export const ViewToggle = () => {
  const viewMode = useStore((s) => s.viewMode);
  const setViewMode = useStore((s) => s.setViewMode);
  const maximizedPane = useStore((s) => s.maximizedPane);
  const setMaximizedPane = useStore((s) => s.setMaximizedPane);
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
