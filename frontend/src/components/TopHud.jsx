import React from 'react';
import { useStore } from '../store/useStore';

export const TopHud = () => {
  const connectionState = useStore((s) => s.connectionState);
  const device = useStore((s) => s.device);
  const metrics = useStore((s) => s.metrics);
  const bestScore = useStore((s) => s.bestScore);
  const episode = useStore((s) => s.episode);
  const step = useStore((s) => s.step);
  const boundaries = useStore((s) => s.boundaries);
  const totalSiteArea = useStore((s) => s.totalSiteArea);

  const fillPct = Math.round((metrics.fillRatio || 0) * 100);
  const rentablePct = Math.round((metrics.rentableRatio || 0) * 100);
  const filledArea = Math.round((metrics.fillRatio || 0) * totalSiteArea);
  const scoreVal = typeof metrics.score === 'number' ? metrics.score.toFixed(1) : '-40.0';
  const bestVal = typeof bestScore === 'number' ? bestScore.toFixed(1) : '--';

  return (
    <header className="top-hud-bar">
      <div className="hud-brand-center">
        <div className="hud-title-row">
          <svg className="brand-mark" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect x="1" y="1" width="9" height="9" rx="1.5" fill="#a9c071" opacity="0.8"/>
            <rect x="6" y="6" width="9" height="9" rx="1.5" fill="#a9c071" stroke="#111712" strokeWidth="1.5"/>
            <path d="M6 1v5H1" stroke="#111712" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
          <span className="hud-brand-title">
            MODULE LAB <span className="version-tag">v0.9.0-alpha</span>
          </span>
          <div className="hud-status-group">
            <span className="connection-badge" data-state={connectionState}>
              <span className="status-dot"></span>
              <span>{connectionState === 'connected' ? 'Connected' : connectionState === 'connecting' ? 'Connecting' : 'Offline'}</span>
            </span>
            <span className="device-badge">DEVICE {device}</span>
          </div>
        </div>

        <div className="metric-strip">
          <div className="metric-card">
            <span className="metric-label">SCORE</span>
            <strong className="metric-val">{scoreVal}</strong>
            <span className="metric-sub">Best {bestVal}</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">AVG. FILL</span>
            <strong className="metric-val">{fillPct}%</strong>
            <span className="metric-sub">{filledArea} m² filled</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">RENTABLE</span>
            <strong className="metric-val">{rentablePct}%</strong>
            <span className="metric-sub">of filled area</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">EPISODE</span>
            <strong className="metric-val">{String(episode).padStart(3, '0')}</strong>
            <span className="metric-sub">{boundaries.length} floors</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">STEP</span>
            <strong className="metric-val">{String(step).padStart(3, '0')}</strong>
            <span className="metric-sub">modules placed</span>
          </div>
        </div>
      </div>
    </header>
  );
};
