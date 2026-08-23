import React from 'react';
import { useStore } from '../store/useStore';

export const ViewToggle = () => {
  const viewMode = useStore((s) => s.viewMode);
  const setViewMode = useStore((s) => s.setViewMode);

  return (
    <div className="view-mode-pill glass-card">
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
    </div>
  );
};

export default ViewToggle;
