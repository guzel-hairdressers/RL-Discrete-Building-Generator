import React from 'react';
import { useStore } from '../store/useStore';

export const BottomDock = () => {
  const mode = useStore((s) => s.mode);
  const setMode = useStore((s) => s.setMode);
  const phase = useStore((s) => s.phase);
  const trainingWanted = useStore((s) => s.trainingWanted);
  const toggleTraining = useStore((s) => s.toggleTraining);
  const requestNewSite = useStore((s) => s.requestNewSite);
  const resetPolicy = useStore((s) => s.resetPolicy);
  const setResetConfirmOpen = useStore((s) => s.setResetConfirmOpen);
  const saveCheckpoint = useStore((s) => s.saveCheckpoint);
  const loadCheckpoint = useStore((s) => s.loadCheckpoint);
  const disableMerging = useStore((s) => s.disableMerging);
  const toggleMerging = useStore((s) => s.toggleMerging);
  const settingsOpen = useStore((s) => s.settingsOpen);
  const setSettingsOpen = useStore((s) => s.setSettingsOpen);

  const isTraining = mode === 'training';
  const actionTitle = isTraining
    ? (trainingWanted ? 'Pause Training (Space)' : 'Start Training (Space)')
    : (trainingWanted ? 'Stop Generating (Space)' : '▶ Generate (Space)');

  return (
    <div className="bottom-dock-bar glass-dock">
      {/* Mode Switcher Pill */}
      <div className="dock-mode-group">
        <button
          type="button"
          className={`dock-mode-btn ${mode === 'training' ? 'active' : ''}`}
          onClick={() => setMode('training')}
        >
          Training
        </button>
        <button
          type="button"
          className={`dock-mode-btn ${mode === 'inference' ? 'active' : ''}`}
          onClick={() => setMode('inference')}
        >
          Inference
        </button>
      </div>

      {/* Primary Action Button */}
      <button
        type="button"
        className={`dock-btn dock-btn-primary ${trainingWanted ? 'pause-active' : ''}`}
        onClick={toggleTraining}
      >
        <span>{actionTitle}</span>
      </button>

      {/* New Site Button */}
      <button
        type="button"
        className="dock-btn dock-btn-compact"
        onClick={requestNewSite}
        title="Load New Real Urban Site (N)"
      >
        ＋ New Site (N)
      </button>

      {/* Merging Toggle */}
      <button
        type="button"
        className={`dock-btn dock-btn-compact ${disableMerging ? 'btn-active' : ''}`}
        onClick={toggleMerging}
        title="Toggle BPE Merging (M)"
      >
        {disableMerging ? 'Enable Merging (M)' : 'Disable Merging (M)'}
      </button>

      {/* Reset Button (Only in Training Mode) */}
      {isTraining && (
        <button
          type="button"
          className="dock-btn dock-btn-compact"
          onClick={() => setResetConfirmOpen(true)}
          title="Reset Model Weights (R)"
        >
          ↺ Reset (R)
        </button>
      )}

      {/* Save Button (Only in Training Mode) */}
      {isTraining && (
        <button
          type="button"
          className="dock-btn dock-btn-compact"
          onClick={saveCheckpoint}
          title="Save Checkpoint (S)"
        >
          ↓ Save (S)
        </button>
      )}

      {/* Load Button */}
      <label className="dock-btn dock-btn-compact" style={{ cursor: 'pointer', margin: 0 }}>
        ↑ Load (L)
        <input
          type="file"
          accept=".pt"
          style={{ display: 'none' }}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) {
              const reader = new FileReader();
              reader.onload = () => {
                const b64 = btoa(
                  new Uint8Array(reader.result).reduce((d, byte) => d + String.fromCharCode(byte), '')
                );
                loadCheckpoint(b64);
              };
              reader.readAsArrayBuffer(file);
            }
          }}
        />
      </label>

      {/* Settings Toggle */}
      <button
        type="button"
        className={`dock-btn dock-btn-compact ${settingsOpen ? 'btn-active' : ''}`}
        onClick={() => setSettingsOpen(!settingsOpen)}
        title="Open Configuration Panel"
      >
        ⚙ Settings
      </button>
    </div>
  );
};
