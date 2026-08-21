import React from 'react';
import { useStore } from '../store/useStore';

export const ResetModal = () => {
  const resetConfirmOpen = useStore((s) => s.resetConfirmOpen);
  const setResetConfirmOpen = useStore((s) => s.setResetConfirmOpen);
  const resetPolicy = useStore((s) => s.resetPolicy);

  if (!resetConfirmOpen) return null;

  return (
    <div className="confirm-modal-overlay">
      <div className="confirm-modal-content glass-card">
        <h3>Reset policy weights?</h3>
        <p>This will erase all training progress and reset model weights to random initialization.</p>
        <div className="confirm-modal-buttons">
          <button
            type="button"
            className="confirm-btn cancel-btn"
            onClick={() => setResetConfirmOpen(false)}
          >
            Cancel
          </button>
          <button
            type="button"
            className="confirm-btn reset-btn"
            onClick={resetPolicy}
          >
            Yes, Reset
          </button>
        </div>
      </div>
    </div>
  );
};
