import React, { useEffect, useRef } from 'react';
import { useStore } from '../store/useStore';

const CATEGORY_COLORS = {
  core: '#dc745d',
  corridor: '#e1ba57',
  room: '#a9c5ae',
  special: '#6e9c89',
};

export const PlanCanvas2D = () => {
  const canvasRef = useRef(null);
  const viewRef = useRef({
    zoom: 6,
    panX: 40,
    panY: 80,
    isPanning: false,
    startX: 0,
    startY: 0,
  });

  const boundaries = useStore((s) => s.boundaries);
  const individualPlacementsList = useStore((s) => s.individualPlacementsList);
  const currentMergedPlacements = useStore((s) => s.currentMergedPlacements);
  const disableMerging = useStore((s) => s.disableMerging);
  const hoveredModuleId = useStore((s) => s.hoveredModuleId);
  const setMaximizedPane = useStore((s) => s.setMaximizedPane);

  // Canvas Pan / Zoom Event Handlers
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const handlePointerDown = (e) => {
      viewRef.current.isPanning = true;
      viewRef.current.startX = e.clientX - viewRef.current.panX;
      viewRef.current.startY = e.clientY - viewRef.current.panY;
      canvas.style.cursor = 'grabbing';
    };

    const handlePointerMove = (e) => {
      if (!viewRef.current.isPanning) return;
      viewRef.current.panX = e.clientX - viewRef.current.startX;
      viewRef.current.panY = e.clientY - viewRef.current.startY;
      render();
    };

    const handlePointerUp = () => {
      viewRef.current.isPanning = false;
      canvas.style.cursor = 'grab';
    };

    const handleWheel = (e) => {
      e.preventDefault();
      const zoomFactor = e.deltaY < 0 ? 1.15 : 0.85;
      const rect = canvas.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;

      viewRef.current.panX = mouseX - (mouseX - viewRef.current.panX) * zoomFactor;
      viewRef.current.panY = mouseY - (mouseY - viewRef.current.panY) * zoomFactor;
      viewRef.current.zoom = Math.max(1, Math.min(80, viewRef.current.zoom * zoomFactor));
      render();
    };

    canvas.addEventListener('pointerdown', handlePointerDown);
    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
    canvas.addEventListener('wheel', handleWheel, { passive: false });

    return () => {
      canvas.removeEventListener('pointerdown', handlePointerDown);
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
      canvas.removeEventListener('wheel', handleWheel);
    };
  }, []);

  // Main 2D Render Loop
  const render = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const { zoom, panX, panY } = viewRef.current;

    // Resize buffer to canvas client size
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
    }

    ctx.clearRect(0, 0, w, h);
    ctx.save();
    ctx.translate(panX, panY);
    ctx.scale(zoom, zoom);

    // 1. Draw Floor Sites
    boundaries.forEach((boundary, idx) => {
      const outer = boundary.outer || [];
      if (outer.length < 3) return;

      ctx.beginPath();
      outer.forEach((pt, pIdx) => {
        const px = Number(pt.x || pt[0] || 0);
        const py = Number(pt.y || pt[1] || 0);
        if (pIdx === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      });
      ctx.closePath();

      // Floor Background Fill & Border
      ctx.fillStyle = '#fbfaf8';
      ctx.fill();
      ctx.strokeStyle = '#111712';
      ctx.lineWidth = 1.8 / zoom;
      ctx.stroke();

      // Floor Label
      if (outer.length > 0) {
        const floorName = `FLOOR ${String(idx + 1).padStart(2, '0')} · SITE ${Math.round(boundary.siteArea || 0)} m²`;
        ctx.save();
        ctx.fillStyle = '#64748b';
        ctx.font = `bold ${Math.max(2, 9 / zoom)}px monospace`;
        ctx.fillText(floorName, outer[0].x || 0, (outer[0].y || 0) - 4 / zoom);
        ctx.restore();
      }
    });

    // 2. Draw Module Placements
    const effectiveList = (!disableMerging && currentMergedPlacements.length > 0)
      ? currentMergedPlacements
      : individualPlacementsList;

    effectiveList.forEach((placement) => {
      const poly = placement.poly || placement.polygon || placement.mergedPolygon || placement.coords;
      if (!Array.isArray(poly) || poly.length < 3) return;

      const cat = placement.category || (placement.module ? placement.module.category : 'room');
      const color = CATEGORY_COLORS[cat] || '#a9c5ae';

      ctx.beginPath();
      poly.forEach((pt, pIdx) => {
        const px = Number(pt.x || pt[0] || 0);
        const py = Number(pt.y || pt[1] || 0);
        if (pIdx === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      });
      ctx.closePath();

      ctx.fillStyle = color;
      ctx.fill();
      ctx.strokeStyle = '#111712';
      ctx.lineWidth = 1.0 / zoom;
      ctx.stroke();
    });

    ctx.restore();

    // 3. Draw Dynamic Pixel Scale Bar
    drawScaleBar(ctx, w, h, zoom);
  };

  const drawScaleBar = (ctx, width, height, zoom) => {
    const targetMeters = [50, 25, 10, 5, 2, 1].find((m) => m * zoom >= 40 && m * zoom <= 180) || 10;
    const barPx = targetMeters * zoom;
    const x = width - barPx - 24;
    const y = height - 24;

    ctx.save();
    ctx.fillStyle = '#111712';
    ctx.strokeStyle = '#111712';
    ctx.lineWidth = 2;

    ctx.beginPath();
    ctx.moveTo(x, y - 4);
    ctx.lineTo(x, y);
    ctx.lineTo(x + barPx, y);
    ctx.lineTo(x + barPx, y - 4);
    ctx.stroke();

    ctx.font = 'bold 10px monospace';
    ctx.textAlign = 'center';
    ctx.fillText(`${targetMeters}m`, x + barPx / 2, y - 6);
    ctx.restore();
  };

  // Re-render whenever boundaries or placements change
  useEffect(() => {
    render();
  }, [boundaries, individualPlacementsList, currentMergedPlacements, disableMerging, hoveredModuleId]);

  return (
    <div className="right-2d-pane">
      <canvas ref={canvasRef} id="planCanvas" style={{ width: '100%', height: '100%', display: 'block' }} />
      <div className="pane-top-actions right-top-actions">
        <button
          type="button"
          className="glass-icon-btn"
          onClick={() => setMaximizedPane('right')}
          title="Maximize 2D Floor Plans"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/>
          </svg>
        </button>
      </div>
    </div>
  );
};
