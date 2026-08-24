import React, { useEffect, useRef, useCallback } from 'react';
import { useStore } from '../store/useStore';

const CATEGORY_COLORS = {
  core: '#ff4d4d',     // Pure vibrant red for core
  corridor: '#ccccff', // HSL 240, 100%, 90% light blue
  room: '#ccccff',     // HSL 240, 100%, 90% light blue
  special: '#ccccff',  // HSL 240, 100%, 90% light blue
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
  const completed3DPlacements = useStore((s) => s.completed3DPlacements);
  const phase = useStore((s) => s.phase);
  const disableMerging = useStore((s) => s.disableMerging);
  const hoveredModuleId = useStore((s) => s.hoveredModuleId);
  const maximizedPane = useStore((s) => s.maximizedPane);
  const setMaximizedPane = useStore((s) => s.setMaximizedPane);
  const isMaximized = maximizedPane === 'right';

  // Exact Architectural Crenellated Stepped Scale Bar (Context Generator Standard)
  const drawArchitecturalScaleBar = (ctx, canvasWidth, zoom) => {
    const targetWidth = Math.max(90, Math.min(160, canvasWidth * 0.14));
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

    const rightMargin = 68;
    const x = canvasWidth - totalBarWidth - rightMargin;
    const y_top = 26;
    const y_bottom = 33;

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

  // Core 2D Plan Render Kernel (1:1 Native Pixel Resolution, Zero Stretching)
  const render = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const w = window.innerWidth;
    const h = window.innerHeight;

    // Strict 1:1 hardware buffer resolution matching viewport
    const expectedW = Math.round(w * dpr);
    const expectedH = Math.round(h * dpr);
    if (canvas.width !== expectedW || canvas.height !== expectedH) {
      canvas.width = expectedW;
      canvas.height = expectedH;
    }

    ctx.save();
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);

    const { zoom, panX, panY } = viewRef.current;

    ctx.save();
    ctx.translate(panX, panY);
    ctx.scale(zoom, zoom);

    // 1. Draw Multi-Floor Boundaries (Solid Crisp Black Outlines)
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

      // Floor Boundary Perimeter (Crisp Black)
      ctx.strokeStyle = '#0f172a';
      ctx.lineWidth = 1.35 / zoom;
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

    // 2. Draw Placed Building Modules (Red Core, Blue Normal Blocks, Black Outlines)
    const isRunning = phase === 'running';
    const effectivePlacements = (isRunning || disableMerging)
      ? individualPlacementsList
      : ((currentMergedPlacements && currentMergedPlacements.length > 0)
          ? currentMergedPlacements
          : ((completed3DPlacements && completed3DPlacements.length > 0)
              ? completed3DPlacements
              : individualPlacementsList));

    effectivePlacements.forEach((placement) => {
      const isHovered = hoveredModuleId && placement.id === hoveredModuleId;
      const components = placement.components;

      if (Array.isArray(components) && components.length > 1) {
        // 1. Fill each constituent sub-component with its true color (Red for Core, Blue for Room)
        components.forEach((comp) => {
          const cPoly = comp.poly || comp.polygon || comp.coords;
          if (!Array.isArray(cPoly) || cPoly.length < 3) return;
          const cCat = comp.category || (comp.module ? comp.module.category : 'room');
          const isCore = cCat === 'core' || comp.isCore || comp.coreStackLocked || (comp.id && String(comp.id).toLowerCase().includes('core')) || (comp.module && (comp.module.category === 'core' || comp.module.coreStackLocked));
          const fillColor = isHovered ? '#60a5fa' : (isCore ? CATEGORY_COLORS.core : CATEGORY_COLORS.room);

          ctx.beginPath();
          cPoly.forEach((p, pIdx) => {
            const px = Number(p.x ?? p[0] ?? 0);
            const py = Number(p.y ?? p[1] ?? 0);
            if (pIdx === 0) ctx.moveTo(px, py);
            else ctx.lineTo(px, py);
          });
          ctx.closePath();
          ctx.fillStyle = fillColor;
          ctx.fill();
        });

        // 2. Stroke ONLY the outer merged macro-polygon in solid black!
        const outerPoly = placement.poly || placement.polygon || placement.mergedPolygon || placement.coords;
        if (Array.isArray(outerPoly) && outerPoly.length >= 3) {
          ctx.beginPath();
          outerPoly.forEach((p, pIdx) => {
            const px = Number(p.x ?? p[0] ?? 0);
            const py = Number(p.y ?? p[1] ?? 0);
            if (pIdx === 0) ctx.moveTo(px, py);
            else ctx.lineTo(px, py);
          });
          ctx.closePath();
          ctx.strokeStyle = isHovered ? '#0284c7' : '#000000';
          ctx.lineWidth = (isHovered ? 2.2 : 1.35) / zoom;
          ctx.lineJoin = 'round';
          ctx.stroke();
        }
      } else {
        // Single unmerged placement
        const poly = placement.poly || placement.polygon || placement.coords;
        if (!Array.isArray(poly) || poly.length < 3) return;

        const cat = placement.category || (placement.module ? placement.module.category : 'room');
        const isCore = cat === 'core' || placement.isCore || placement.coreStackLocked || (placement.id && String(placement.id).toLowerCase().includes('core')) || (placement.module && (placement.module.category === 'core' || placement.module.coreStackLocked));
        const baseColor = isCore ? CATEGORY_COLORS.core : CATEGORY_COLORS.room;

        ctx.beginPath();
        poly.forEach((p, pIdx) => {
          const px = Number(p.x ?? p[0] ?? 0);
          const py = Number(p.y ?? p[1] ?? 0);
          if (pIdx === 0) ctx.moveTo(px, py);
          else ctx.lineTo(px, py);
        });
        ctx.closePath();

        ctx.fillStyle = isHovered ? '#60a5fa' : baseColor;
        ctx.fill();

        ctx.strokeStyle = isHovered ? '#0284c7' : '#000000';
        ctx.lineWidth = (isHovered ? 2.2 : 1.35) / zoom;
        ctx.lineJoin = 'round';
        ctx.stroke();
      }
    });

    ctx.restore();

    // 3. Draw Staggered Architectural Graphic Scale Bar (Black, Anchored Top Right)
    drawArchitecturalScaleBar(ctx, w, zoom);

    ctx.restore();
  }, [boundaries, individualPlacementsList, currentMergedPlacements, completed3DPlacements, phase, disableMerging, hoveredModuleId]);

  // Schedule render via requestAnimationFrame
  const scheduleRender = useCallback(() => {
    if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    animFrameRef.current = requestAnimationFrame(render);
  }, [render]);

  // Calculate framing bounding box and target center
  const getFraming = useCallback((maximized) => {
    if (!boundaries || boundaries.length === 0) return null;

    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    boundaries.forEach((b) => {
      const outer = b.outer || [];
      outer.forEach((p) => {
        const px = Number(p.x ?? p[0] ?? 0);
        const py = Number(p.y ?? p[1] ?? 0);
        if (px < minX) minX = px;
        if (py < minY) minY = py;
        if (px > maxX) maxX = px;
        if (py > maxY) maxY = py;
      });
    });

    if (!Number.isFinite(minX)) return null;

    const boundsW = Math.max(10, maxX - minX);
    const boundsH = Math.max(10, maxY - minY);
    const boundsCenterX = minX + boundsW / 2;
    const boundsCenterY = minY + boundsH / 2;

    const canvasW = window.innerWidth || 1440;
    const canvasH = window.innerHeight || 900;
    
    // In split view, the 2D view is visible in the right half -> center is canvasW * 0.75
    // In maximized view, the 2D view occupies the full screen -> center is canvasW * 0.50
    const targetCenterX = maximized ? (canvasW * 0.50) : (canvasW * 0.75);
    const targetCenterY = canvasH / 2 - 20;

    const fitW = (maximized ? (canvasW * 0.84) : (canvasW * 0.44));
    const fitH = canvasH * 0.65;
    const optimalZoom = Math.max(1.0, Math.min(25.0, Math.min(fitW / boundsW, fitH / boundsH)));

    return {
      zoom: optimalZoom,
      panX: targetCenterX - boundsCenterX * optimalZoom,
      panY: targetCenterY - boundsCenterY * optimalZoom,
    };
  }, [boundaries]);

  // Initial Auto-Fit on new site boundaries
  const lastBoundariesRef = useRef(null);
  useEffect(() => {
    if (boundaries && boundaries.length > 0 && boundaries !== lastBoundariesRef.current) {
      lastBoundariesRef.current = boundaries;
      const framing = getFraming(isMaximized);
      if (framing) {
        viewRef.current.zoom = framing.zoom;
        viewRef.current.panX = framing.panX;
        viewRef.current.panY = framing.panY;
        scheduleRender();
      }
    }
  }, [boundaries, isMaximized, getFraming, scheduleRender]);

  // Smooth 0.5s Slide Transition to Center when Expanding / Restoring Split View
  useEffect(() => {
    const framing = getFraming(isMaximized);
    if (!framing) return;

    let animId;
    const start = performance.now();
    const duration = 500;
    const initialPanX = viewRef.current.panX;
    const initialZoom = viewRef.current.zoom;
    const targetPanX = framing.panX;
    const targetZoom = framing.zoom;

    const step = (now) => {
      const elapsed = now - start;
      const progress = Math.min(1, elapsed / duration);
      // Smooth quartic ease matching CSS cubic-bezier(0.16, 1, 0.3, 1)
      const p = 1 - progress;
      const ease = 1 - p * p * p * p;
      viewRef.current.panX = initialPanX + (targetPanX - initialPanX) * ease;
      viewRef.current.zoom = initialZoom + (targetZoom - initialZoom) * ease;
      render();
      if (progress < 1) {
        animId = requestAnimationFrame(step);
      }
    };
    animId = requestAnimationFrame(step);

    return () => cancelAnimationFrame(animId);
  }, [isMaximized, getFraming, render]);

  // Window Resize & Event Handlers
  useEffect(() => {
    const handleResize = () => {
      scheduleRender();
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [scheduleRender]);

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
      const mouseX = e.clientX;
      const mouseY = e.clientY;

      // Snappy CAD Zoom Rate
      const delta = e.deltaY;
      const speed = e.deltaMode === 1 ? 0.065 : 0.0085;
      const zoomFactor = Math.exp(-delta * speed);
      const newZoom = Math.max(0.5, Math.min(300.0, viewRef.current.zoom * zoomFactor));

      viewRef.current.panX = mouseX - (mouseX - viewRef.current.panX) * (newZoom / viewRef.current.zoom);
      viewRef.current.panY = mouseY - (mouseY - viewRef.current.panY) * (newZoom / viewRef.current.zoom);
      viewRef.current.zoom = newZoom;

      scheduleRender();
    };

    canvas.addEventListener('pointerdown', handlePointerDown);
    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
    canvas.addEventListener('wheel', handleWheel, { passive: false });

    scheduleRender();

    return () => {
      canvas.removeEventListener('pointerdown', handlePointerDown);
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
      canvas.removeEventListener('wheel', handleWheel);
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    };
  }, [scheduleRender]);

  // Trigger render when boundaries or placements update
  useEffect(() => {
    scheduleRender();
  }, [boundaries, individualPlacementsList, currentMergedPlacements, scheduleRender]);

  return (
    <div className={`right-2d-pane ${isMaximized ? 'pane-maximized' : ''}`}>
      <canvas
        ref={canvasRef}
        style={{
          position: 'absolute',
          top: 0,
          right: 0,
          width: '100vw',
          height: '100vh',
          display: 'block',
          cursor: 'grab',
          touchAction: 'none',
        }}
      />

      {/* Split-View Expand / Collapse Button */}
      <button
        type="button"
        className="pane-expand-btn right-expand"
        onClick={() => setMaximizedPane(isMaximized ? null : 'right')}
        title={isMaximized ? 'Restore Split View' : 'Expand 2D Plan View (100%)'}
      >
        {isMaximized ? (
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="4 14 10 14 10 20" />
            <polyline points="20 10 14 10 14 4" />
            <line x1="14" y1="10" x2="21" y2="3" />
            <line x1="3" y1="21" x2="10" y2="14" />
          </svg>
        ) : (
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="15 3 21 3 21 9" />
            <polyline points="9 21 3 21 3 15" />
            <line x1="21" y1="3" x2="14" y2="10" />
            <line x1="3" y1="21" x2="10" y2="14" />
          </svg>
        )}
      </button>
    </div>
  );
};

export default PlanCanvas2D;
