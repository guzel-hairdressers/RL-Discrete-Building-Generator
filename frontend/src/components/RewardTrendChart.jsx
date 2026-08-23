import React, { useRef, useState, useEffect } from 'react';
import { useStore } from '../store/useStore';

export const RewardTrendChart = () => {
  const canvasRef = useRef(null);
  const rewardHistory = useStore((s) => s.rewardHistory);
  const metrics = useStore((s) => s.metrics);
  const [showFullHistory, setShowFullHistory] = useState(false);
  const [hoverData, setHoverData] = useState(null); // { ep, reward, x, y }
  const [hoverFactor, setHoverFactor] = useState(0); // 0 (smoothed) to 1 (fit)
  const hoverAnimRef = useRef(null);

  // Raw values array
  const rawValues = rewardHistory.length > 0 ? rewardHistory : [metrics.score || -40];
  const totalEpisodes = rawValues.length;

  // Sliced values for crop (last 100 or full)
  const isCropped = !showFullHistory && totalEpisodes > 100;
  const values = isCropped ? rawValues.slice(-100) : rawValues;
  const startEp = isCropped ? totalEpisodes - values.length + 1 : 1;

  // Window Smoothing Function (Adaptive Gaussian-Weighted Moving Window from v0.7)
  const computeWindowSmoothedPoints = (rawVals, basePoints) => {
    if (rawVals.length < 2) return basePoints;
    const n = rawVals.length;
    const k = Math.max(1, Math.min(8, Math.floor(n / 7)));
    const sigma = Math.max(0.8, k * 0.55);

    return basePoints.map((pt, i) => {
      let sumY = 0;
      let sumW = 0;
      const start = Math.max(0, i - k);
      const end = Math.min(n - 1, i + k);
      for (let j = start; j <= end; j++) {
        const dist = Math.abs(j - i);
        const w = Math.exp(-(dist * dist) / (2 * sigma * sigma));
        sumY += basePoints[j].y * w;
        sumW += w;
      }
      return { x: pt.x, y: sumY / sumW };
    });
  };

  // Regression Fit Function (Quadratic / Polynomial Fit from v0.7)
  const computeFittedPoints = (rawVals, basePoints) => {
    const n = rawVals.length;
    if (n < 3) return basePoints;

    const m = 3; // Quadratic fit
    const A = Array.from({ length: m }, () => new Float64Array(m + 1));
    const sumsU = new Float64Array(5);
    const sumsUY = new Float64Array(3);

    for (let i = 0; i < n; i++) {
      const u = n > 1 ? i / (n - 1) : 0;
      const y = basePoints[i].y;
      let uPow = 1;
      for (let p = 0; p < 5; p++) {
        sumsU[p] += uPow;
        if (p < 3) sumsUY[p] += uPow * y;
        uPow *= u;
      }
    }

    for (let r = 0; r < m; r++) {
      for (let c = 0; c < m; c++) {
        A[r][c] = sumsU[r + c];
      }
      A[r][m] = sumsUY[r];
    }

    for (let col = 0; col < m; col++) {
      let maxRow = col;
      for (let row = col + 1; row < m; row++) {
        if (Math.abs(A[row][col]) > Math.abs(A[maxRow][col])) maxRow = row;
      }
      if (maxRow !== col) {
        const tmp = A[col];
        A[col] = A[maxRow];
        A[maxRow] = tmp;
      }
      if (Math.abs(A[col][col]) < 1e-12) continue;

      for (let row = 0; row < m; row++) {
        if (row === col) continue;
        const factor = A[row][col] / A[col][col];
        for (let k = col; k <= m; k++) {
          A[row][k] -= factor * A[col][k];
        }
      }
    }

    const c0 = A[0][m] / A[0][0];
    const c1 = A[1][m] / A[1][1];
    const c2 = A[2][m] / A[2][2];

    return basePoints.map((pt, i) => {
      const u = n > 1 ? i / (n - 1) : 0;
      const fitY = c0 + c1 * u + c2 * (u * u);
      return { x: pt.x, y: fitY };
    });
  };

  // Render Canvas Chart
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth || 320;
    const h = canvas.clientHeight || 36;

    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
    }

    ctx.save();
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);

    const marginLeft = 26;
    const marginRight = 8;
    const marginTop = 3;
    const marginBottom = 10;
    const gridW = w - marginLeft - marginRight;
    const gridH = h - marginTop - marginBottom;

    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = Math.max(6, max - min);

    // Y-Axis Numerical Labels
    ctx.font = '500 7.5px Inter, system-ui, sans-serif';
    ctx.fillStyle = '#64748b';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    ctx.fillText(max.toFixed(0), marginLeft - 4, marginTop + 2);
    ctx.fillText(min.toFixed(0), marginLeft - 4, marginTop + gridH);

    // X-Axis Epoch Labels
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText(`Ep ${startEp}`, marginLeft, h - marginBottom + 1);
    ctx.textAlign = 'right';
    ctx.fillText(`Ep ${totalEpisodes}`, w - marginRight, h - marginBottom + 1);

    // Grid Baseline Lines
    ctx.strokeStyle = '#e2e8f0';
    ctx.lineWidth = 0.8;
    ctx.beginPath();
    ctx.moveTo(marginLeft, marginTop + gridH);
    ctx.lineTo(marginLeft + gridW, marginTop + gridH);
    ctx.stroke();

    const n = values.length;
    const basePoints = values.map((val, idx) => ({
      x: marginLeft + (n > 1 ? (idx / (n - 1)) * gridW : gridW / 2),
      y: marginTop + gridH - ((val - min) / span) * gridH,
    }));

    // Area Fill
    if (basePoints.length > 1) {
      const grad = ctx.createLinearGradient(0, marginTop, 0, marginTop + gridH);
      grad.addColorStop(0, 'rgba(16, 185, 129, 0.18)');
      grad.addColorStop(1, 'rgba(16, 185, 129, 0.0)');
      ctx.beginPath();
      ctx.moveTo(basePoints[0].x, marginTop + gridH);
      for (const pt of basePoints) ctx.lineTo(pt.x, pt.y);
      ctx.lineTo(basePoints[basePoints.length - 1].x, marginTop + gridH);
      ctx.closePath();
      ctx.fillStyle = grad;
      ctx.fill();
    }

    // Raw trace
    ctx.beginPath();
    basePoints.forEach((pt, idx) => {
      if (idx === 0) ctx.moveTo(pt.x, pt.y);
      else ctx.lineTo(pt.x, pt.y);
    });
    ctx.strokeStyle = 'rgba(16, 185, 129, 0.3)';
    ctx.lineWidth = 1;
    ctx.stroke();

    // Smoothed vs Fit Line Crossfade
    const smoothed = computeWindowSmoothedPoints(values, basePoints);
    const fitted = computeFittedPoints(values, basePoints);

    ctx.beginPath();
    for (let i = 0; i < n; i++) {
      const sx = smoothed[i].x;
      const sy = smoothed[i].y * (1 - hoverFactor) + fitted[i].y * hoverFactor;
      if (i === 0) ctx.moveTo(sx, sy);
      else ctx.lineTo(sx, sy);
    }
    ctx.strokeStyle = hoverFactor > 0.5 ? '#2563eb' : '#059669';
    ctx.lineWidth = 1.75;
    ctx.stroke();

    // Active End Point Dot
    if (basePoints.length > 0) {
      const last = basePoints[basePoints.length - 1];
      ctx.fillStyle = '#059669';
      ctx.beginPath();
      ctx.arc(last.x, last.y, 2.5, 0, Math.PI * 2);
      ctx.fill();
    }

    ctx.restore();
  }, [values, totalEpisodes, startEp, hoverFactor]);

  // Pointer interactions for Hover & Fitting
  const handlePointerMove = (e) => {
    const canvas = canvasRef.current;
    if (!canvas || values.length === 0) return;
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const marginLeft = 26;
    const marginRight = 8;
    const gridW = rect.width - marginLeft - marginRight;

    const relX = Math.max(0, Math.min(gridW, mouseX - marginLeft));
    const idx = Math.round((relX / gridW) * (values.length - 1));
    const epNum = startEp + idx;
    const rewardVal = values[idx];

    setHoverData({ ep: epNum, reward: rewardVal, clientX: e.clientX, clientY: e.clientY });
    setHoverFactor(1.0);
  };

  const handlePointerLeave = () => {
    setHoverData(null);
    setHoverFactor(0.0);
  };

  return (
    <div
      className="reward-trend-wrap"
      onPointerMove={handlePointerMove}
      onPointerLeave={handlePointerLeave}
    >
      <div className="trend-header">
        <span className="trend-title">REWARD TREND</span>
        {totalEpisodes > 100 && (
          <button
            type="button"
            className="crop-toggle-btn"
            onClick={() => setShowFullHistory(!showFullHistory)}
            title="Toggle last 100 episodes vs all episodes"
          >
            {showFullHistory ? 'All Ep' : 'Last 100'}
          </button>
        )}
      </div>

      <canvas
        ref={canvasRef}
        style={{
          width: '100%',
          height: '36px',
          display: 'block',
          cursor: 'crosshair',
        }}
      />

      {hoverData && (
        <div
          className="trend-tooltip"
          style={{
            position: 'fixed',
            left: `${hoverData.clientX + 8}px`,
            top: `${hoverData.clientY - 30}px`,
            zIndex: 1000,
          }}
        >
          <strong>Ep {hoverData.ep}</strong> · {hoverData.reward?.toFixed(1)}
        </div>
      )}
    </div>
  );
};

export default RewardTrendChart;
