import React from 'react';
import { useStore } from '../store/useStore';

export const SettingsDrawer = () => {
  const settingsOpen = useStore((s) => s.settingsOpen);
  const setSettingsOpen = useStore((s) => s.setSettingsOpen);
  const settings = useStore((s) => s.settings);
  const updateSettings = useStore((s) => s.updateSettings);

  if (!settingsOpen) return null;

  return (
    <aside className="settings-drawer glass-panel">
      <div className="drawer-header">
        <h3>Optimizer Settings</h3>
        <button className="glass-icon-btn" onClick={() => setSettingsOpen(false)}>✕</button>
      </div>

      <div className="drawer-body">
        <div className="form-group">
          <label>Boundary Family</label>
          <select
            className="custom-select full-width"
            value={settings.boundaryType}
            onChange={(e) => updateSettings({ boundaryType: e.target.value })}
          >
            <option value="real">Real site (OSM parcel)</option>
            <option value="mixed">Mixed random (Real &amp; Procedural)</option>
            <option value="free">Free procedural</option>
            <option value="lobed">Multi-lobed star</option>
            <option value="rect">Rectangle</option>
            <option value="convex">Convex hull</option>
          </select>
        </div>

        <div className="form-group">
          <label>Site Area Tier</label>
          <select
            className="custom-select full-width"
            value={settings.siteAreaTier}
            onChange={(e) => updateSettings({ siteAreaTier: e.target.value })}
          >
            <option value="ANY">Any size (Procedural / Real)</option>
            <option value="XS">XS (&lt; 250 m²)</option>
            <option value="S">S (250 – 500 m²)</option>
            <option value="M">M (500 – 1,500 m²)</option>
            <option value="L">L (1,500 – 3,500 m²)</option>
            <option value="XL">XL (&gt; 3,500 m²)</option>
          </select>
        </div>

        <div className="form-group">
          <label>Atrium Strategy</label>
          <select
            className="custom-select full-width"
            value={settings.atriumPolicy}
            onChange={(e) => updateSettings({ atriumPolicy: e.target.value })}
          >
            <option value="none">No atrium</option>
            <option value="central">Central atrium</option>
          </select>
        </div>

        <div className="form-group checkbox-group">
          <label>
            <input
              type="checkbox"
              checked={settings.singleFloor}
              onChange={(e) => updateSettings({ singleFloor: e.target.checked })}
            />
            <span>Single-floor mode</span>
          </label>
        </div>

        <div className="form-group checkbox-group">
          <label>
            <input
              type="checkbox"
              checked={settings.publicMode}
              onChange={(e) => updateSettings({ publicMode: e.target.checked })}
            />
            <span>Public / office mode</span>
          </label>
        </div>

        <div className="form-group">
          <label>Parallel Stories ({settings.parallelEnvironments})</label>
          <input
            type="range"
            min="1"
            max="12"
            value={settings.parallelEnvironments}
            onChange={(e) => updateSettings({ parallelEnvironments: parseInt(e.target.value, 10) })}
          />
        </div>

        <div className="form-group">
          <label>Max Modules per Floor ({settings.maxModules})</label>
          <input
            type="range"
            min="20"
            max="200"
            value={settings.maxModules}
            onChange={(e) => updateSettings({ maxModules: parseInt(e.target.value, 10) })}
          />
        </div>
      </div>
    </aside>
  );
};
