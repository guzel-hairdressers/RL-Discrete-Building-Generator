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

  // Architectural Staggered Scale Bar Function
  const drawArchitecturalScaleBar = (ctx, canvasWidth, zoom) => {
    // Select standard metric step (5m, 10m, 20m, 50m, 100m, 200m)
    const targetPixelWidth = 140;
    const rawMeters = targetPixelWidth / zoom;
    const niceSteps = [1, 2, 5, 10, 20, 50, 100, 200, 500];
    let stepMeters = niceSteps[0];
    for (const step of niceSteps) {
      if (step * zoom <= 180) stepMeters = step;
      else break;
    }

    const totalMeters = stepMeters * 2;
    const segWidth = stepMeters * zoom;
    const barWidth = totalMeters * zoom;
    const barHeight = 6;
    const rightMargin = 58;
    const topMargin = 14;
    const startX = canvasWidth - barWidth - rightMargin;
    const startY = topMargin + 12;

    ctx.save();

    // Background Badge
    ctx.fillStyle = 'rgba(255, 255, 255, 0.92)';
    ctx.strokeStyle = '#cbd5e1';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(startX - 12, topMargin - 8, barWidth + 24, 42, 6);
    ctx.fill();
    ctx.stroke();

    // Scale Header Label
    ctx.font = '600 9px Inter, system-ui, sans-serif';
    ctx.fillStyle = '#475569';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText('METRIC SCALE', startX, topMargin - 3);

    // Staggered Alternating Blocks (Top Half vs Bottom Half)
    // Segment 1 (0 to stepMeters): Black Left, White Right
    ctx.fillStyle = '#0f172a';
    ctx.fillRect(startX, startY, segWidth / 2, barHeight / 2);
    ctx.fillRect(startX + segWidth / 2, startY + barHeight / 2, segWidth / 2, barHeight / 2);

    // Segment 2 (stepMeters to totalMeters): Black Left, White Right
    ctx.fillRect(startX + segWidth, startY, segWidth / 2, barHeight / 2);
    ctx.fillRect(startX + segWidth + segWidth / 2, startY + barHeight / 2, segWidth / 2, barHeight / 2);

    // Outline around entire scale bar
    ctx.strokeStyle = '#0f172a';
    ctx.lineWidth = 1;
    ctx.strokeRect(startX, startY, barWidth, barHeight);

    // Tick Marks & Metric Number Labels
    ctx.font = '500 9px Inter, system-ui, sans-serif';
    ctx.fillStyle = '#0f172a';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';

    // 0m
    ctx.fillText('0', startX, startY + barHeight + 3);
    // Middle step
    ctx.fillText(`${stepMeters}m`, startX + segWidth, startY + barHeight + 3);
    // End step
    ctx.fillText(`${totalMeters}m`, startX + barWidth, startY + barHeight + 3);

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
