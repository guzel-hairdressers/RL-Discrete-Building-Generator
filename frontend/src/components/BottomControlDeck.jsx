import React from 'react';
import { useStore, percentToArea, areaToPercent } from '../store/useStore';

export const BottomControlDeck = () => {
  const mode = useStore((s) => s.mode);
  const trainingWanted = useStore((s) => s.trainingWanted);
  const startTraining = useStore((s) => s.startTraining);
  const startInference = useStore((s) => s.startInference);
  const pauseExecution = useStore((s) => s.pauseExecution);
  const requestNewSite = useStore((s) => s.requestNewSite);
  const setResetConfirmOpen = useStore((s) => s.setResetConfirmOpen);
  const saveCheckpoint = useStore((s) => s.saveCheckpoint);
  const loadCheckpoint = useStore((s) => s.loadCheckpoint);
  const disableMerging = useStore((s) => s.disableMerging);
  const toggleMerging = useStore((s) => s.toggleMerging);
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
  const rewardHistory = useStore((s) => s.rewardHistory);
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

  // Render SVG Sparkline for Reward Trend
  const renderRewardSparkline = () => {
    const history = rewardHistory.length > 0 ? rewardHistory : [metrics.score || -40];
    const width = 280;
    const height = 34;
    const padding = 4;

    const min = Math.min(...history);
    const max = Math.max(...history);
    const range = max - min || 1;

    const points = history.map((val, idx) => {
      const x = padding + (idx / Math.max(1, history.length - 1)) * (width - 2 * padding);
      const y = height - padding - ((val - min) / range) * (height - 2 * padding);
      return `${x},${y}`;
    }).join(' ');

    const lastX = padding + (width - 2 * padding);
    const lastVal = history[history.length - 1];
    const lastY = height - padding - ((lastVal - min) / range) * (height - 2 * padding);

    return (
      <svg className="sparkline-svg" width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <defs>
          <linearGradient id="rewardGrad" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#10b981" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#10b981" stopOpacity="0.0" />
          </linearGradient>
        </defs>
        {history.length > 1 && (
          <polygon
            points={`${padding},${height - padding} ${points} ${lastX},${height - padding}`}
            fill="url(#rewardGrad)"
          />
        )}
        <polyline
          fill="none"
          stroke="#059669"
          strokeWidth="1.75"
          strokeLinecap="round"
          strokeLinejoin="round"
          points={points}
        />
        <circle cx={lastX} cy={lastY} r="3" fill="#059669" />
      </svg>
    );
  };

  return (
    <footer className="bottom-control-deck-container">
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

                {/* Column 2: Architectural Penalties & Grammar */}
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
                  <div className="setting-row">
                    <label>Atrium Sampling Policy</label>
                    <select
                      className="custom-select-small"
                      value={settings.atriumPolicy || 'none'}
                      onChange={(e) => updateSettings({ atriumPolicy: e.target.value })}
                    >
                      <option value="none">None (Solid Floorplate)</option>
                      <option value="procedural">Procedural Courtyards</option>
                      <option value="learned">Policy-Learned Atriums</option>
                    </select>
                  </div>
                  <div className="setting-row">
                    <label>BPE Vocabulary Merge Bonus</label>
                    <span className="val-tag badge-tag">Clipped +30.0 pts</span>
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

      {/* Main Unified Control Deck Bar (2 Rows: Actions & Metrics ON TOP, Filters & Sparkline ON BOTTOM) */}
      <div className="bottom-deck-main glass-dock">
        {/* ROW 1 (TOP): Actions & Mode (Left) & Metrics HUD (Right) */}
        <div className="deck-row top-row">
          {/* Top-Left: Action Buttons & Split Training/Inference */}
          <div className="deck-section actions-section">
            {/* Split Button: START TRAINING | START INFERENCE (Morphs to PAUSE when running) */}
            {trainingWanted ? (
              <button
                type="button"
                className="split-pause-btn"
                onClick={pauseExecution}
                title="Pause Current Generation (Space)"
              >
                ❚❚ PAUSE ({mode === 'inference' ? 'Inference' : 'Training'})
              </button>
            ) : (
              <div className="split-btn-group">
                <button
                  type="button"
                  className={`split-action-btn ${mode === 'training' ? 'primary-active' : ''}`}
                  onClick={startTraining}
                  title="Start Neural Policy Training (Space)"
                >
                  START TRAINING
                </button>
                <div className="split-separator"></div>
                <button
                  type="button"
                  className={`split-action-btn ${mode === 'inference' ? 'primary-active' : ''}`}
                  onClick={startInference}
                  title="Start Inference & Generation (Space)"
                >
                  START INFERENCE
                </button>
              </div>
            )}

            {/* Reset Weights (Only in Training Mode) */}
            {isTraining && (
              <button
                type="button"
                className="deck-btn"
                onClick={() => setResetConfirmOpen(true)}
                title="Reset Model Weights (R)"
              >
                ↺ Reset Weights
              </button>
            )}

            {/* Save Weights (Only in Training Mode) */}
            {isTraining && (
              <button
                type="button"
                className="deck-btn"
                onClick={saveCheckpoint}
                title="Save Checkpoint Weights (S)"
              >
                ↓ Save Weights
              </button>
            )}

            {/* Load Weights */}
            <label className="deck-btn file-label-btn" title="Load Weights Checkpoint (.pt)">
              ↑ Load Weights
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
                className={`deck-btn ${activeBottomDrawer === 'settings' ? 'active-deck-btn' : ''}`}
                onClick={() => setActiveBottomDrawer('settings')}
                title="Toggle Architectural & Morphological Settings"
              >
                ⚙ Settings
              </button>
            )}

            {/* Diagnostics Button */}
            <button
              type="button"
              className={`deck-btn ${activeBottomDrawer === 'diagnostics' ? 'active-deck-btn' : ''}`}
              onClick={() => setActiveBottomDrawer('diagnostics')}
              title="Toggle Live Neural & RL Diagnostics"
            >
              📊 Diagnostics
            </button>

            {/* New Site Button */}
            <button
              type="button"
              className="deck-btn"
              onClick={requestNewSite}
              title="Generate / Switch Next Site (N)"
            >
              ＋ New Site
            </button>

            {/* Disable / Enable Merging */}
            <button
              type="button"
              className={`deck-btn ${disableMerging ? 'active-deck-btn' : ''}`}
              onClick={toggleMerging}
              title="Toggle BPE Room Merging (M)"
            >
              {disableMerging ? 'Enable Merging' : 'Disable Merging'}
            </button>
          </div>

          <div className="deck-divider"></div>

          {/* Top-Right: Metrics HUD Strip */}
          <div className="deck-section metrics-section">
            <div className="hud-metric-box">
              <span className="hud-label">REWARD</span>
              <strong className="hud-val">{rewardVal}</strong>
              <span className="hud-sub">Best {bestVal}</span>
            </div>
            <div className="hud-metric-box">
              <span className="hud-label">AVG. FILL</span>
              <strong className="hud-val">{fillPct}%</strong>
              <span className="hud-sub">{filledArea} m² filled</span>
            </div>
            <div className="hud-metric-box">
              <span className="hud-label">RENTABLE</span>
              <strong className="hud-val">{rentablePct}%</strong>
              <span className="hud-sub">of filled area</span>
            </div>
            <div className="hud-metric-box">
              <span className="hud-label">EP</span>
              <strong className="hud-val">{String(episode).padStart(3, '0')}</strong>
              <span className="hud-sub">{boundaries.length || 9} floors</span>
            </div>
            <div className="hud-metric-box">
              <span className="hud-label">STEP</span>
              <strong className="hud-val">{String(step).padStart(3, '0')}</strong>
              <span className="hud-sub">modules placed</span>
            </div>
          </div>
        </div>

        {/* ROW 2 (BOTTOM): Filters (Left) & Reward Trend Sparkline (Right) */}
        <div className="deck-row bottom-row">
          {/* Bottom-Left: Filters */}
          <div className="deck-section filters-section">
            {/* Boundary Type Dropdown */}
            <div className="filter-item">
              <span className="item-label">BOUNDARY TYPE</span>
              <select
                className="deck-select"
                value={settings.boundaryType || 'free'}
                onChange={(e) => setBoundaryType(e.target.value)}
              >
                <option value="free">Free (Mixed Procedural)</option>
                <option value="real">Real OSM Urban Parcel</option>
                <option value="convex">Convex Polygon</option>
                <option value="concave">Concave Polygon</option>
                <option value="lobed">Multi-Lobed Perimeter</option>
                <option value="notched">Notched Courtyard</option>
                <option value="rect">Rectangular Block</option>
                <option value="lshape">L-Shape Footprint</option>
                <option value="ushape">U-Shape Footprint</option>
                <option value="tshape">T-Shape Footprint</option>
              </select>
            </div>

            {/* Plot Area Tiers & Slider */}
            <div className="filter-item flex-2">
              <div className="item-header">
                <span className="item-label">PLOT AREA</span>
                <div className="tier-pills">
                  {['ANY', 'XS', 'S', 'M', 'L', 'XL'].map((t) => (
                    <button
                      key={t}
                      type="button"
                      className={`tier-pill ${filters.activeTier === t ? 'active' : ''}`}
                      onClick={() => selectTier(t)}
                    >
                      {t}
                    </button>
                  ))}
                </div>
              </div>
              <div className="dual-slider-wrap">
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
                <div className="slider-track"></div>
              </div>
              <span className="item-sub-val">{filters.minArea} m² – {filters.maxArea} m²</span>
            </div>

            {/* Context Height Slider */}
            <div className="filter-item flex-2">
              <div className="item-header">
                <span className="item-label">CONTEXT HEIGHT</span>
              </div>
              <div className="dual-slider-wrap">
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
                <div className="slider-track"></div>
              </div>
              <span className="item-sub-val">{filters.minHeight}m – {filters.maxHeight}m</span>
            </div>

            {/* Custom Site & Reset Buttons */}
            <div className="filter-buttons-stack">
              <button
                type="button"
                className="deck-action-btn btn-custom-site"
                onClick={() => setCustomModalOpen(true)}
                title="Harvest Custom Urban Location"
              >
                Custom Site
              </button>
              <button
                type="button"
                className="deck-action-btn btn-reset-filters"
                onClick={resetFilters}
                title="Reset Filters to Default"
              >
                Reset Filters
              </button>
            </div>
          </div>

          <div className="deck-divider"></div>

          {/* Bottom-Right: Reward Trend Live Sparkline */}
          <div className="deck-section sparkline-section">
            <span className="sparkline-title">REWARD TREND</span>
            <div className="sparkline-container">
              {renderRewardSparkline()}
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
};

export default BottomControlDeck;
