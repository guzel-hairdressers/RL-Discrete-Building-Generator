import React, { useEffect, useRef, useCallback } from 'react';
import { useStore } from '../store/useStore';

const CATEGORY_COLORS = {
  core: '#ee7258',     // Terracotta coral
  corridor: '#ebb952', // Warm amber gold
  room: '#9bc2a7',     // Soft sage green
  special: '#649880',  // Pine green
};

export const PlanCanvas2D = () => {
  const canvasRef = useRef(null);
  const animFrameRef = useRef(null);
  const viewRef = useRef({
    zoom: 6.5,
    panX: 60,
    panY: 90,
    isPanning: false,
    startX: 0,
    startY: 0,
  });

  const boundaries = useStore((s) => s.boundaries);
  const individualPlacementsList = useStore((s) => s.individualPlacementsList);
  const currentMergedPlacements = useStore((s) => s.currentMergedPlacements);
  const disableMerging = useStore((s) => s.disableMerging);
  const hoveredModuleId = useStore((s) => s.hoveredModuleId);
  const maximizedPane = useStore((s) => s.maximizedPane);
  const setMaximizedPane = useStore((s) => s.setMaximizedPane);

  // Main 2D Render Routine (HiDPI Retina Vector Quality)
  const render = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;

    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
    }

    ctx.save();
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);

    const { zoom, panX, panY } = viewRef.current;

    ctx.save();
    ctx.translate(panX, panY);
    ctx.scale(zoom, zoom);

    // 1. Draw Floor Site Boundaries (Solid Crisp Black Outlines)
    boundaries.forEach((boundary, idx) => {
      const outer = boundary.outer || [];
      if (outer.length < 3) return;

      // Floor Fill (Ultra Light Ghost Wash)
      ctx.beginPath();
      outer.forEach((p, pIdx) => {
        const px = Number(p.x ?? p[0] ?? 0);
        const py = Number(p.y ?? p[1] ?? 0);
        if (pIdx === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      });
      ctx.closePath();
      ctx.fillStyle = 'rgba(248, 250, 252, 0.7)';
      ctx.fill();

      // Floor Boundary Perimeter
      ctx.strokeStyle = '#0f172a';
      ctx.lineWidth = 1.6 / zoom;
      ctx.lineJoin = 'miter';
      ctx.stroke();

      // Floor Label
      const floorLabel = `FLOOR ${String(idx + 1).padStart(2, '0')} · SITE ${Math.round(boundary.siteArea || boundary.exactArea || 0)} m²`;
      ctx.font = `600 ${Math.max(10 / zoom, 1.2)}px Inter, system-ui, sans-serif`;
      ctx.fillStyle = '#475569';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'top';

      const minX = Math.min(...outer.map(p => Number(p.x ?? p[0] ?? 0)));
      const maxY = Math.max(...outer.map(p => Number(p.y ?? p[1] ?? 0)));
      ctx.fillText(floorLabel, minX, maxY + 2.5 / zoom);
    });

    // 2. Draw Placed Building Modules (Individual or Merged)
    const effectivePlacements = (!disableMerging && currentMergedPlacements.length > 0)
      ? currentMergedPlacements
      : individualPlacementsList;

    effectivePlacements.forEach((placement) => {
      const poly = placement.poly || placement.polygon || placement.mergedPolygon || placement.coords;
      if (!Array.isArray(poly) || poly.length < 3) return;

      const cat = placement.category || (placement.module ? placement.module.category : 'room');
      const baseColor = CATEGORY_COLORS[cat] || CATEGORY_COLORS.room;
      const isHovered = hoveredModuleId && placement.id === hoveredModuleId;

      ctx.beginPath();
      poly.forEach((p, pIdx) => {
        const px = Number(p.x ?? p[0] ?? 0);
        const py = Number(p.y ?? p[1] ?? 0);
        if (pIdx === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      });
      ctx.closePath();

      // Module Polygon Fill
      ctx.fillStyle = isHovered ? '#38bdf8' : baseColor;
      ctx.fill();

      // Module Architectural Edge Outline
      ctx.strokeStyle = isHovered ? '#0284c7' : '#1e293b';
      ctx.lineWidth = (isHovered ? 2.2 : 1.2) / zoom;
      ctx.lineJoin = 'round';
      ctx.stroke();
    });

    ctx.restore();

    // 3. Draw Staggered Architectural Graphic Scale Bar (Top-Right Overlay)
    drawArchitecturalScaleBar(ctx, w, zoom);

    ctx.restore();
  }, [boundaries, individualPlacementsList, currentMergedPlacements, disableMerging, hoveredModuleId]);

  // Schedule render via requestAnimationFrame
  const scheduleRender = useCallback(() => {
    if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    animFrameRef.current = requestAnimationFrame(render);
  }, [render]);

  // Exact Architectural Crenellated Stepped Scale Bar (Context Generator Standard)
  const drawArchitecturalScaleBar = (ctx, canvasWidth, zoom) => {
    const targetWidth = Math.max(90, Math.min(160, canvasWidth * 0.16));
    const rawD = targetWidth / (10 * zoom);
    
    const niceDist = (raw) => {
      if (!Number.isFinite(raw) || raw <= 0) return 1;
      const exp = 10 ** Math.floor(Math.log10(raw));
      const norm = raw / exp;
      if (norm <= 1) return exp;
      if (norm <= 2) return 2 * exp;
      if (norm <= 5) return 5 * exp;
      return 10 * exp;
    };

    const distance = niceDist(rawD);
    const factors = [0, 1, 2, 5, 10];
    const offsets = factors.map((f) => f * distance * zoom);
    const totalBarWidth = offsets[offsets.length - 1];

    const rightMargin = 56;
    const x = canvasWidth - totalBarWidth - rightMargin;
    const y = 30;
    const y_top = y - 6;
    const y_bottom = y;

    ctx.save();
    ctx.strokeStyle = '#0f172a';
    ctx.fillStyle = '#0f172a';
    ctx.lineWidth = 1.15;
    ctx.lineCap = 'butt';
    ctx.lineJoin = 'miter';
    ctx.font = '700 8.5px Inter, system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'bottom';

    // 1. Draw the crenellated staggered scale bar line
    ctx.beginPath();
    ctx.moveTo(x + offsets[0], y_bottom);
    ctx.lineTo(x + offsets[0], y_top);

    for (let i = 0; i < offsets.length - 1; i++) {
      const y_level = (i % 2 === 0) ? y_top : y_bottom;
      if (i > 0) {
        const y_prev_level = ((i - 1) % 2 === 0) ? y_top : y_bottom;
        ctx.lineTo(x + offsets[i], y_prev_level);
        ctx.lineTo(x + offsets[i], y_level);
      }
      ctx.lineTo(x + offsets[i + 1], y_level);
    }

    const last_segment_idx = offsets.length - 2;
    const y_last_level = (last_segment_idx % 2 === 0) ? y_top : y_bottom;
    const y_opposite_level = (y_last_level === y_top) ? y_bottom : y_top;
    ctx.lineTo(x + offsets[offsets.length - 1], y_opposite_level);
    ctx.stroke();

    // 2. Draw labels above the scale bar
    offsets.forEach((offset, index) => {
      const factor = factors[index];
      const val = factor * distance;
      const label = index === offsets.length - 1 ? `${val}m` : `${val}`;
      ctx.fillText(label, x + offset, y_top - 3);
    });

    ctx.restore();
  };

  // Event Listeners for Smooth Pointer Pan & Exponential Mouse-Centered Zoom
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
      scheduleRender();
    };

    const handlePointerUp = () => {
      viewRef.current.isPanning = false;
      canvas.style.cursor = 'grab';
    };

    const handleWheel = (e) => {
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;

      const zoomFactor = Math.exp(-e.deltaY * 0.0015);
      const newZoom = Math.max(1.0, Math.min(120.0, viewRef.current.zoom * zoomFactor));

      viewRef.current.panX = mouseX - (mouseX - viewRef.current.panX) * (newZoom / viewRef.current.zoom);
      viewRef.current.panY = mouseY - (mouseY - viewRef.current.panY) * (newZoom / viewRef.current.zoom);
      viewRef.current.zoom = newZoom;

      scheduleRender();
    };

    const handleResize = () => {
      scheduleRender();
    };

    const ro = new ResizeObserver(() => {
      scheduleRender();
    });
    ro.observe(canvas);

    canvas.addEventListener('pointerdown', handlePointerDown);
    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
    canvas.addEventListener('wheel', handleWheel, { passive: false });
    window.addEventListener('resize', handleResize);

    scheduleRender();

    return () => {
      ro.disconnect();
      canvas.removeEventListener('pointerdown', handlePointerDown);
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
      canvas.removeEventListener('wheel', handleWheel);
      window.removeEventListener('resize', handleResize);
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    };
  }, [scheduleRender]);

  // Trigger render when boundaries or placements update
  useEffect(() => {
    scheduleRender();
  }, [boundaries, individualPlacementsList, currentMergedPlacements, scheduleRender]);

  const isMaximized = maximizedPane === 'right';

  return (
    <div className={`right-2d-pane ${isMaximized ? 'pane-maximized' : ''}`}>
      <canvas
        ref={canvasRef}
        style={{
          width: '100%',
          height: '100%',
          display: 'block',
          cursor: 'grab',
          touchAction: 'none',
        }}
      />

      {/* Split-View Expand / Collapse Button */}
      <button
        type="button"
        className="pane-expand-btn right-expand"
        onClick={() => setMaximizedPane('right')}
        title={isMaximized ? 'Restore Split View' : 'Expand 2D Plan View (100%)'}
      >
        {isMaximized ? (
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="4 14 10 14 10 20"></polyline>
            <polyline points="20 10 14 10 14 4"></polyline>
            <line x1="14" y1="10" x2="21" y2="3"></line>
            <line x1="3" y1="21" x2="10" y2="14"></line>
          </svg>
        ) : (
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="15 3 21 3 21 9"></polyline>
            <polyline points="9 21 3 21 3 15"></polyline>
            <line x1="21" y1="3" x2="14" y2="10"></line>
            <line x1="3" y1="21" x2="10" y2="14"></line>
          </svg>
        )}
      </button>
    </div>
  );
};

export default PlanCanvas2D;
