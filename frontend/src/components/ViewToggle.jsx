import React from 'react';
import { useStore } from '../store/useStore';

export const ViewToggle = () => {
  const viewMode = useStore((s) => s.viewMode);
  const setViewMode = useStore((s) => s.setViewMode);

  return (
    <div id="view-toggle" className="glass-pill-toggle">
      <button
        className={`toggle-btn ${viewMode === 'axonometric' ? 'active' : ''}`}
        onClick={() => setViewMode('axonometric')}
      >
        Axonometric
      </button>
      <button
        className={`toggle-btn ${viewMode === 'perspective' ? 'active' : ''}`}
        onClick={() => setViewMode('perspective')}
      >
        Perspective
      </button>
    </div>
  );
};
