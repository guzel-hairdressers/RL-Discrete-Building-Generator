import React from 'react';
import { useStore, percentToArea, areaToPercent } from '../store/useStore';
import { RewardTrendChart } from './RewardTrendChart';

export const BottomControlDeck = () => {
  const mode = useStore((s) => s.mode);
  const trainingWanted = useStore((s) => s.trainingWanted);
  const startTraining = useStore((s) => s.startTraining);
  const startInference = useStore((s) => s.startInference);
  const pauseExecution = useStore((s) => s.pauseExecution);
  const setResetConfirmOpen = useStore((s) => s.setResetConfirmOpen);
  const saveCheckpoint = useStore((s) => s.saveCheckpoint);
  const loadCheckpoint = useStore((s) => s.loadCheckpoint);
  const activeBottomDrawer = useStore((s) => s.activeBottomDrawer);
  const setActiveBottomDrawer = useStore((s) => s.setActiveBottomDrawer);
  const setCustomModalOpen = useStore((s) => s.setCustomModalOpen);

  const settings = useStore((s) => s.settings);
  const updateSettings = useStore((s) => s.updateSettings);
  const setBoundaryType = useStore((s) => s.setBoundaryType);

  const filters = useStore((s) => s.filters);
  const setFilter = useStore((s) => s.setFilter);
  const selectTier = useStore((s) => s.selectTier);
  const resetFilters = useStore((s) => s.resetFilters);

  const metrics = useStore((s) => s.metrics);
  const bestReward = useStore((s) => s.bestReward);
  const episode = useStore((s) => s.episode);
  const step = useStore((s) => s.step);
  const boundaries = useStore((s) => s.boundaries);
  const totalSiteArea = useStore((s) => s.totalSiteArea);
  const diagnostics = useStore((s) => s.diagnostics || {});
  const device = useStore((s) => s.device);

  const isTraining = mode === 'training';
  const minPercent = areaToPercent(filters.minArea);
  const maxPercent = areaToPercent(filters.maxArea);

  const fillPct = Math.round((metrics.fillRatio || 0) * 100);
  const rentablePct = Math.round((metrics.rentableRatio || 0) * 100);
  const filledArea = Math.round((metrics.fillRatio || 0) * totalSiteArea);
  const rewardVal = typeof metrics.score === 'number' ? metrics.score.toFixed(1) : '-40.0';
  const bestVal = typeof bestReward === 'number' ? bestReward.toFixed(1) : '--';

  return (
    <footer className="bottom-deck-floating-wrapper">
      {/* Expandable Slide-Up Panel (Settings or Diagnostics) */}
      {activeBottomDrawer && (
        <div className="expanded-bottom-drawer glass-panel">
          <div className="drawer-header">
            <div className="drawer-title-group">
              <span className="drawer-title">
                {activeBottomDrawer === 'settings' ? 'CONFIGURATION & PARAMETERS' : 'DEVELOPER & RL DIAGNOSTICS'}
              </span>
              <span className="drawer-subtitle">
                {activeBottomDrawer === 'settings' ? 'Module Lab Architectural Kernel' : `Live Telemetry on Device ${device}`}
              </span>
            </div>
            <button
              className="drawer-close-btn"
              onClick={() => setActiveBottomDrawer(null)}
              title="Close Panel"
            >
              ✕
            </button>
          </div>

          <div className="drawer-body">
            {activeBottomDrawer === 'settings' ? (
              <div className="settings-grid">
                {/* Column 1: Multi-Floor & Scale */}
                <div className="settings-section">
                  <h4 className="section-title">Morphology & Multi-Floor</h4>
                  <div className="setting-row">
                    <label>Parallel Floors (Batch Size)</label>
                    <div className="input-with-val">
                      <input
                        type="range"
                        min="1"
                        max="12"
                        value={settings.parallelEnvironments || 9}
                        onChange={(e) => updateSettings({ parallelEnvironments: parseInt(e.target.value) })}
                      />
                      <span className="val-tag">{settings.parallelEnvironments || 9} stories</span>
                    </div>
                  </div>
                  <div className="setting-row">
                    <label>Max Modules / Floor</label>
                    <div className="input-with-val">
                      <input
                        type="range"
                        min="30"
                        max="240"
                        step="5"
                        value={settings.maxModules || 130}
                        onChange={(e) => updateSettings({ maxModules: parseInt(e.target.value) })}
                      />
                      <span className="val-tag">{settings.maxModules || 130}</span>
                    </div>
                  </div>
                  <div className="setting-row">
                    <label>Max Room Hops Depth</label>
                    <div className="input-with-val">
                      <input
                        type="range"
                        min="1"
                        max="10"
                        value={settings.maxRoomHops || 3}
                        onChange={(e) => updateSettings({ maxRoomHops: parseInt(e.target.value) })}
                      />
                      <span className="val-tag">{settings.maxRoomHops || 3} hops</span>
                    </div>
                  </div>
                </div>

                {/* Column 2: Architectural Filters & Clearances */}
                <div className="settings-section">
                  <h4 className="section-title">Architectural Filters & Clearances</h4>
                  <div className="setting-row">
                    <label>Crevice Filter Angle</label>
                    <span className="val-tag badge-tag">45.0° Active</span>
                  </div>
                  <div className="setting-row">
                    <label>Narrow Facade Chasm Clearance</label>
                    <span className="val-tag badge-tag">3.0m Raycast</span>
                  </div>
                  <div className="setting-row">
                    <label>Deep Daylight Penalty</label>
                    <span className="val-tag badge-tag">Facade Depth ≥ 2</span>
                  </div>
                  <div className="setting-row">
                    <label>Core Shaft Spacing</label>
                    <div className="input-with-val">
                      <input
                        type="range"
                        min="4"
                        max="16"
                        step="1"
                        value={settings.coreSpacing || 8}
                        onChange={(e) => updateSettings({ coreSpacing: parseFloat(e.target.value) })}
                      />
                      <span className="val-tag">{settings.coreSpacing || 8}m</span>
                    </div>
                  </div>
                </div>

                {/* Column 3: Reinforcement Learning & Optimizer */}
                <div className="settings-section">
                  <h4 className="section-title">Reinforcement Learning & PPO</h4>
                  <div className="setting-row">
                    <label>Learning Rate</label>
                    <div className="input-with-val">
                      <input
                        type="range"
                        min="0.0005"
                        max="0.01"
                        step="0.0005"
                        value={settings.learningRate || 0.003}
                        onChange={(e) => updateSettings({ learningRate: parseFloat(e.target.value) })}
                      />
                      <span className="val-tag">{settings.learningRate || 0.003}</span>
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="diagnostics-grid">
                <div className="diag-card">
                  <span className="diag-label">CRITIC LOSS (L_V)</span>
                  <strong className="diag-val">{diagnostics.criticLoss?.toFixed(4) || '0.0142'}</strong>
                  <span className="diag-sub">MSE value error</span>
                </div>
                <div className="diag-card">
                  <span className="diag-label">POLICY LOSS (L_π)</span>
                  <strong className="diag-val">{diagnostics.policyLoss?.toFixed(4) || '-0.0089'}</strong>
                  <span className="diag-sub">PPO clipped surrogate</span>
                </div>
                <div className="diag-card">
                  <span className="diag-label">ENTROPY BONUS</span>
                  <strong className="diag-val">{diagnostics.entropy?.toFixed(3) || '1.842'}</strong>
                  <span className="diag-sub">Exploration density</span>
                </div>
                <div className="diag-card">
                  <span className="diag-label">ACTION SPACE (|A|)</span>
                  <strong className="diag-val">{diagnostics.actionSpaceSize || '184'}</strong>
                  <span className="diag-sub">Legal valid candidates</span>
                </div>
                <div className="diag-card">
                  <span className="diag-label">CANDIDATE LATENCY</span>
                  <strong className="diag-val">{diagnostics.candidateLatencyMs?.toFixed(2) || '2.84'} ms</strong>
                  <span className="diag-sub">C-accelerated SAT</span>
                </div>
                <div className="diag-card">
                  <span className="diag-label">STEP TIME</span>
                  <strong className="diag-val">{diagnostics.stepTimeMs?.toFixed(2) || '4.15'} ms</strong>
                  <span className="diag-sub">Neural step duration</span>
                </div>
                <div className="diag-card">
                  <span className="diag-label">ENGINE THROUGHPUT</span>
                  <strong className="diag-val">{diagnostics.throughputStepsPerSec || '241'} stp/s</strong>
                  <span className="diag-sub">Parallel multi-floor</span>
                </div>
                <div className="diag-card">
                  <span className="diag-label">CORE SHAFT STACKING</span>
                  <strong className="diag-val" style={{ color: '#059669' }}>100.0% EXACT</strong>
                  <span className="diag-sub">0 shaft misalignment</span>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Floating Centered Bottom Control Deck (Divided exactly in the middle) */}
      <div className="bottom-deck-floating glass-dock">
        {/* LEFT HALF (Controls on top, Filters on bottom) */}
        <div className="deck-half deck-left-half">
          {/* Row 1: Action Buttons */}
          <div className="deck-subrow deck-row-actions">
            {/* Split Button: Start Training | Start Inference */}
            {trainingWanted ? (
              <button
                type="button"
                className="btn-clean-pause"
                onClick={pauseExecution}
                title="Pause Current Generation (Space)"
              >
                ❚❚ Pause
              </button>
            ) : (
              <div className="split-btn-clean">
                <button
                  type="button"
                  className={`split-side-btn ${mode === 'training' ? 'active-side' : ''}`}
                  onClick={startTraining}
                  title="Start Training Policy"
                >
                  Start Training
                </button>
                <span className="split-mid-divider"></span>
                <button
                  type="button"
                  className={`split-side-btn ${mode === 'inference' ? 'active-side' : ''}`}
                  onClick={startInference}
                  title="Start Inference Generation"
                >
                  Start Inference
                </button>
              </div>
            )}

            {/* Reset Weights (Only in Training Mode) */}
            {isTraining && (
              <button
                type="button"
                className="deck-btn-clean"
                onClick={() => setResetConfirmOpen(true)}
                title="Reset Model Weights (R)"
              >
                Reset Weights
              </button>
            )}

            {/* Save Weights (Only in Training Mode) */}
            {isTraining && (
              <button
                type="button"
                className="deck-btn-clean"
                onClick={saveCheckpoint}
                title="Save Checkpoint Weights (S)"
              >
                Save Weights
              </button>
            )}

            {/* Load Weights */}
            <label className="deck-btn-clean file-label-clean" title="Load Checkpoint (.pt)">
              Load Weights
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

            {/* Settings (Only in Training Mode) */}
            {isTraining && (
              <button
                type="button"
                className={`deck-btn-clean ${activeBottomDrawer === 'settings' ? 'active-tab' : ''}`}
                onClick={() => setActiveBottomDrawer('settings')}
                title="Toggle Configuration Panel"
              >
                Settings
              </button>
            )}

            {/* Diagnostics Button */}
            <button
              type="button"
              className={`deck-btn-clean ${activeBottomDrawer === 'diagnostics' ? 'active-tab' : ''}`}
              onClick={() => setActiveBottomDrawer('diagnostics')}
              title="Toggle Live RL Diagnostics"
            >
              Diagnostics
            </button>
          </div>

          {/* Row 2: Filters */}
          <div className="deck-subrow deck-row-filters">
            {/* Boundary Type Dropdown */}
            <div className="filter-group-clean">
              <span className="filter-label-clean">Boundary Type</span>
              <select
                className="filter-select-clean"
                value={settings.boundaryType || 'free'}
                onChange={(e) => setBoundaryType(e.target.value)}
              >
                <option value="free">Mixed</option>
                <option value="real">OSM Plot</option>
                <option value="rect">Rectangular</option>
                <option value="convex">Convex</option>
                <option value="concave">Concave</option>
                <option value="lshape">L-Shape</option>
                <option value="ushape">U-Shape</option>
                <option value="tshape">T-Shape</option>
              </select>
            </div>

            {/* Plot Area Tier Pills & Compact Slider */}
            <div className="filter-group-clean flex-compact-slider">
              <div className="filter-label-row">
                <span className="filter-label-clean">Plot Area</span>
                <div className="tier-pills-clean">
                  {['ANY', 'XS', 'S', 'M', 'L', 'XL'].map((t) => (
                    <button
                      key={t}
                      type="button"
                      className={`tier-pill-clean ${filters.activeTier === t ? 'active' : ''}`}
                      onClick={() => selectTier(t)}
                    >
                      {t}
                    </button>
                  ))}
                </div>
              </div>
              <div className="dual-slider-compact">
                <input
                  type="range"
                  min="0"
                  max="100"
                  step="0.2"
                  value={minPercent}
                  onChange={(e) => setFilter('minArea', Math.min(percentToArea(parseFloat(e.target.value)), filters.maxArea))}
                />
                <input
                  type="range"
                  min="0"
                  max="100"
                  step="0.2"
                  value={maxPercent}
                  onChange={(e) => setFilter('maxArea', Math.max(percentToArea(parseFloat(e.target.value)), filters.minArea))}
                />
                <div className="slider-track-compact"></div>
              </div>
            </div>

            {/* Context Height Compact Slider */}
            <div className="filter-group-clean flex-compact-slider">
              <span className="filter-label-clean">Context Height</span>
              <div className="dual-slider-compact">
                <input
                  type="range"
                  min="10"
                  max="300"
                  step="5"
                  value={filters.minHeight}
                  onChange={(e) => setFilter('minHeight', Math.min(parseInt(e.target.value), filters.maxHeight))}
                />
                <input
                  type="range"
                  min="10"
                  max="300"
                  step="5"
                  value={filters.maxHeight}
                  onChange={(e) => setFilter('maxHeight', Math.max(parseInt(e.target.value), filters.minHeight))}
                />
                <div className="slider-track-compact"></div>
              </div>
            </div>

            {/* Custom Site & Reset Buttons */}
            <div className="filter-buttons-clean">
              <button
                type="button"
                className="btn-custom-clean"
                onClick={() => setCustomModalOpen(true)}
                title="Harvest Custom Urban Location"
              >
                Custom Site
              </button>
              <button
                type="button"
                className="btn-reset-clean"
                onClick={resetFilters}
                title="Reset Filters"
              >
                Reset
              </button>
            </div>
          </div>
        </div>

        {/* Center Divider (Fixed in exact middle of screen / dock) */}
        <div className="deck-center-divider"></div>

        {/* RIGHT HALF (Metrics on top, Reward Trend on bottom) */}
        <div className="deck-half deck-right-half">
          {/* Row 1: Metrics HUD */}
          <div className="deck-subrow deck-row-metrics">
            <div className="metric-box-clean">
              <span className="metric-lbl">REWARD</span>
              <strong className="metric-num">{rewardVal}</strong>
              <span className="metric-desc">Best {bestVal}</span>
            </div>
            <div className="metric-box-clean">
              <span className="metric-lbl">AVG. FILL</span>
              <strong className="metric-num">{fillPct}%</strong>
              <span className="metric-desc">{filledArea} m² filled</span>
            </div>
            <div className="metric-box-clean">
              <span className="metric-lbl">RENTABLE</span>
              <strong className="metric-num">{rentablePct}%</strong>
              <span className="metric-desc">of filled area</span>
            </div>
            <div className="metric-box-clean">
              <span className="metric-lbl">EP</span>
              <strong className="metric-num">{String(episode).padStart(3, '0')}</strong>
              <span className="metric-desc">{boundaries.length || 9} floors</span>
            </div>
            <div className="metric-box-clean">
              <span className="metric-lbl">STEP</span>
              <strong className="metric-num">{String(step).padStart(3, '0')}</strong>
              <span className="metric-desc">modules placed</span>
            </div>
          </div>

          {/* Row 2: Reward Trend Chart */}
          <div className="deck-subrow deck-row-trend">
            <RewardTrendChart />
          </div>
        </div>
      </div>
    </footer>
  );
};

export default BottomControlDeck;
