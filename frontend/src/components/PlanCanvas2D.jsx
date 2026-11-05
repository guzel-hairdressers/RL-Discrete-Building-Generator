import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Maximize2, MousePointer2 } from 'lucide-react';
import { useStore } from '../store/useStore';
import { moduleColor, displayPolygon } from '../store/presentation';

const xy = (p) => [Number(p.x ?? p[0]), -Number(p.y ?? p[1])];
const polygon = (ctx, points) => {
  ctx.beginPath(); points.forEach((p, i) => { const [x,y] = xy(p); i ? ctx.lineTo(x,y) : ctx.moveTo(x,y); }); ctx.closePath();
};
const contains = (point, poly) => {
  let inside = false;
  for (let i=0,j=poly.length-1;i<poly.length;j=i++) {
    const [x,y]=xy(poly[i]), [a,b]=xy(poly[j]);
    if ((y>point[1]) !== (b>point[1]) && point[0] < (a-x)*(point[1]-y)/(b-y)+x) inside=!inside;
  }
  return inside;
};
export function PlanCanvas2D() {
  const canvas = useRef(null), container = useRef(null);
  const camera = useRef({ zoom: 4, x: 0, y: 0 });
  const pointer = useRef(null), frame = useRef(null), lastSite = useRef('');
  const [size, setSize] = useState({ width: 800, height: 600 });
  const s = useStore();
  const stateRef = useRef(s); stateRef.current = s;
  const visibleBoundaries = s.boundaries.filter((_, i) => s.selectedFloor === 'all' || i === Number(s.selectedFloor));
  const fit = useCallback(() => {
    const state = stateRef.current;
    const points = state.boundaries.filter((_,i) => state.selectedFloor === 'all' || i === Number(state.selectedFloor)).flatMap((b) => b.outer || []).map(xy);
    if (!points.length || !container.current) return;
    const { width, height } = container.current.getBoundingClientRect();
    const xs=points.map((p) => p[0]), ys=points.map((p) => p[1]);
    const minX=Math.min(...xs), maxX=Math.max(...xs), minY=Math.min(...ys), maxY=Math.max(...ys);
    const zoom=Math.min((width-90)/Math.max(10,maxX-minX), (height-100)/Math.max(10,maxY-minY));
    camera.current={ zoom: Math.max(.05,zoom), x:width/2-(minX+maxX)/2*zoom, y:height/2-(minY+maxY)/2*zoom };
    redraw.current();
  }, []);
  const draw = useCallback(() => {
    if (!canvas.current) return;
    const ctx=canvas.current.getContext('2d');
    const { width:w, height:h }=size, dpr=window.devicePixelRatio || 1;
    if (canvas.current.width !== Math.round(w*dpr) || canvas.current.height !== Math.round(h*dpr)) {
      canvas.current.width=Math.round(w*dpr); canvas.current.height=Math.round(h*dpr);
    }
    ctx.setTransform(dpr,0,0,dpr,0,0); ctx.clearRect(0,0,w,h);
    const { zoom:z,x,y }=camera.current;
    ctx.save(); ctx.translate(x,y); ctx.scale(z,z);
    const visibleFloor = (f) => s.selectedFloor === 'all' || Number(f) === Number(s.selectedFloor);
    for (const [i,b] of s.boundaries.entries()) {
      if (!visibleFloor(i)) continue;
      polygon(ctx,b.outer || []); ctx.fillStyle='#ffffff'; ctx.fill(); ctx.strokeStyle='#9b9b9b'; ctx.lineWidth=1.2/z; ctx.stroke();
      for (const hole of b.holes || []) { polygon(ctx,hole); ctx.fillStyle='#f1f1f1'; ctx.fill(); ctx.setLineDash([4/z,3/z]); ctx.stroke(); ctx.setLineDash([]); }
      const pts=(b.outer || []).map(xy);
      if (pts.length) { ctx.font=`${11/z}px system-ui`; ctx.fillStyle='#9d9d9d'; ctx.fillText(`F${String(i+1).padStart(2,'0')}`,Math.min(...pts.map((p)=>p[0])),Math.max(...pts.map((p)=>p[1]))+18/z); }
    }
    const graph=s.graphState;
    const graphOnly=graph && !graph.realized;
    const placements=graphOnly ? [] : (s.currentMergedPlacements.length ? s.currentMergedPlacements : s.individualPlacementsList);
    for (const p of placements) {
      if (!visibleFloor(p.floor ?? p.instanceIdx ?? p.floorIndex)) continue;
      const poly=displayPolygon(p,s.boundaries); if (poly.length<3) continue;
      const id=p.moduleId || p.module?.id;
      const selected=id===s.selectedModuleId || id===s.hoveredModuleId || p.id===s.selectedOccurrenceId;
      ctx.globalAlpha=s.selectedModuleId && !selected ? .2 : .82;
      polygon(ctx,poly); ctx.fillStyle=moduleColor(id); ctx.fill(); ctx.strokeStyle=selected ? '#6a6a6a' : '#747474'; ctx.lineWidth=(selected?2.8:1)/z; ctx.stroke();
      if (p.category === 'core') { const c=poly.map(xy), cx=c.reduce((a,p)=>a+p[0],0)/c.length, cy=c.reduce((a,p)=>a+p[1],0)/c.length; ctx.font=`bold ${10/z}px system-ui`; ctx.fillStyle='#444444'; ctx.textAlign='center'; ctx.fillText('C',cx,cy); }
    }
    ctx.globalAlpha=1;
    // Explicit planned openings, in site coordinates, with floor offsets.
    ctx.strokeStyle='#16748a';ctx.lineWidth=3/z;ctx.setLineDash([]);ctx.beginPath();
    for (const window of graph?.windows || []) {
      if (!visibleFloor(window.floor)) continue;
      const offset=s.boundaries[window.floor]?.offset || {};
      const [a,b]=window.segment;
      ctx.moveTo(a[0]+(offset.x||0),-a[1]-(offset.y||0));
      ctx.lineTo(b[0]+(offset.x||0),-b[1]-(offset.y||0));
    }
    ctx.stroke();
    const nodes=graph?.nodes || [], byId=new Map(nodes.map((n)=>[n.id,n]));
    const world = (n) => { const b=s.boundaries[n.floor]; return [n.world_x ?? (n.x+(b?.offset?.x || 0)), -(n.world_y ?? (n.y+(b?.offset?.y || 0)))]; };
    const lines=(edges,color,dash) => {
      ctx.strokeStyle=color;ctx.lineWidth=1.5/z;ctx.setLineDash(dash.map((d)=>d/z));ctx.beginPath();
      for (const e of edges || []) {
        const a=byId.get(e.u),b=byId.get(e.v); if (!a || !b || !visibleFloor(a.floor)) continue;
        const p=world(a),q=world(b);ctx.moveTo(...p);ctx.lineTo(...q);
      }
      ctx.stroke();ctx.setLineDash([]);
    };
    if (s.showGraph) lines(graph?.edgesHoriz,'#aaaaaa',[4,4]);
    // Only explicit usable-access edges from the server may be drawn as access.
    if (s.showAccess) lines(graph?.accessEdges,'#6b6b6b',[]);
    if (s.showGraph || graphOnly) for (const n of nodes) {
      if (!visibleFloor(n.floor)) continue;
      const [nx,ny]=world(n), selected=n.id===s.selectedOccurrenceId || n.moduleId===s.selectedModuleId || n.moduleId===s.hoveredModuleId;
      ctx.globalAlpha=s.selectedModuleId && !selected ? .25 : 1;
      ctx.beginPath();ctx.arc(nx,ny,(selected?5:3)/z,0,Math.PI*2);ctx.fillStyle=moduleColor(n.moduleId);ctx.fill();ctx.strokeStyle=selected?'#6a6a6a':'#ffffff';ctx.lineWidth=(selected?2:1)/z;ctx.stroke();
      if (selected && z>2) {ctx.font=`11px system-ui`; ctx.save();ctx.translate(nx,ny);ctx.scale(1/z,1/z);ctx.fillStyle='#444444';ctx.textAlign='left';ctx.fillText(n.moduleId || n.id,9,-7);ctx.restore();}
    }
    ctx.globalAlpha=1;ctx.restore();
    // A scale bar in actual world units, independent of pan and device pixels.
    const units=10**Math.floor(Math.log10(90/z)), length=units*z;
    ctx.strokeStyle='#9d9d9d';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(w-28-length,h-28);ctx.lineTo(w-28,h-28);ctx.stroke();ctx.font='10px system-ui';ctx.textAlign='right';ctx.fillStyle='#9d9d9d';ctx.fillText(`${units} m`,w-28,h-35);
  },[s.boundaries,s.graphState,s.currentMergedPlacements,s.individualPlacementsList,s.selectedFloor,s.selectedModuleId,s.hoveredModuleId,s.selectedOccurrenceId,s.showGraph,s.showAccess,size]);
  const redraw=useRef(()=>{});
  redraw.current=()=>{ cancelAnimationFrame(frame.current); frame.current=requestAnimationFrame(draw); };
  useEffect(()=>{ const observer=new ResizeObserver(([e])=>setSize({width:e.contentRect.width,height:e.contentRect.height})); observer.observe(container.current); return ()=>observer.disconnect(); },[]);
  useEffect(()=>{ redraw.current(); return ()=>cancelAnimationFrame(frame.current); },[draw]);
  useEffect(()=>{
    // Do not fit on graph messages, previews, selection, or component rerenders.
    const signature=JSON.stringify([s.boundaries.map((b)=>b.outer),s.selectedFloor]);
    if (signature !== lastSite.current && visibleBoundaries.length) {lastSite.current=signature;fit();}
  },[s.boundaries,s.selectedFloor,fit,visibleBoundaries.length]);
  useEffect(()=>{fit();},[s.show3D,fit]);
  useEffect(()=>{
    window.addEventListener('reset_views',fit);
    window.addEventListener('fit_plan_layout',fit);
    return()=>{window.removeEventListener('reset_views',fit);window.removeEventListener('fit_plan_layout',fit);};
  },[fit]);
  useEffect(()=>{
    const c=canvas.current;
    const wheel=(e)=>{ e.preventDefault(); const box=c.getBoundingClientRect(), px=e.clientX-box.left,py=e.clientY-box.top;
      const v=camera.current, z=Math.max(.05,Math.min(250,v.zoom*Math.exp(-e.deltaY*.002)));
      camera.current={zoom:z,x:px-(px-v.x)*z/v.zoom,y:py-(py-v.y)*z/v.zoom};redraw.current(); };
    c.addEventListener('wheel',wheel,{passive:false});return()=>c.removeEventListener('wheel',wheel);
  },[]);
  const selectAt=(e)=>{
    const box=canvas.current.getBoundingClientRect(),v=camera.current,pt=[(e.clientX-box.left-v.x)/v.zoom,(e.clientY-box.top-v.y)/v.zoom];
    const state=stateRef.current,nodes=state.graphState?.nodes || [];
    const visible=nodes.filter((n)=>state.selectedFloor==='all' || Number(n.floor)===Number(state.selectedFloor));
    let nearest=null,distance=10/v.zoom;
    for (const n of visible) {const b=state.boundaries[n.floor], nx=n.world_x ?? (n.x+(b?.offset?.x||0)),ny=-(n.world_y ?? (n.y+(b?.offset?.y||0)));const d=Math.hypot(pt[0]-nx,pt[1]-ny);if (d<distance){nearest=n;distance=d;}}
    if (!nearest && state.graphState?.realized) {
      const p=state.individualPlacementsList.find((p)=>(state.selectedFloor==='all'||Number(p.floor ?? p.instanceIdx ?? p.floorIndex)===Number(state.selectedFloor)) && contains(pt,displayPolygon(p,state.boundaries)));
      nearest=p && nodes.find((n)=>n.id===(p.node_id ?? p.id) || (n.moduleId===p.moduleId && n.floor===(p.floor ?? p.instanceIdx ?? p.floorIndex)));
    }
    state.setSelectedOccurrenceId(nearest?.id ?? null);
  };
  return <div className="plan-workspace" ref={container}>
    <canvas ref={canvas} aria-label="Interactive building floor plan. Drag to pan, scroll to zoom, select a room to inspect." onPointerDown={(e)=>{e.currentTarget.setPointerCapture(e.pointerId);pointer.current={x:e.clientX,y:e.clientY,origin:{...camera.current},moved:false};}}
      onPointerMove={(e)=>{const p=pointer.current;if(!p)return;const dx=e.clientX-p.x,dy=e.clientY-p.y;if(Math.hypot(dx,dy)>3)p.moved=true;camera.current={...camera.current,x:p.origin.x+dx,y:p.origin.y+dy};redraw.current();}}
      onPointerUp={(e)=>{if(pointer.current&&!pointer.current.moved)selectAt(e);pointer.current=null;}} onPointerCancel={()=>pointer.current=null} onDoubleClick={fit}/>
    {!s.hasSite && <div className="canvas-empty"><span>⌗</span><h2>A place for possibilities.</h2><p>Connecting to the optimizer to prepare your site.</p></div>}
    <div className="plan-legend"><span><i className="legend-boundary"/>Site boundary</span><span><i className="legend-construction"/>Construction graph</span><span><i style={{display:'inline-block',width:14,borderTop:'3px solid #16748a'}}/>Glazed edges</span>{s.showAccess && <span><i className="legend-access"/>{s.graphState?.accessEdges ? 'Usable access' : 'Access overlay unavailable'}</span>}</div>
    <div className="canvas-tools"><span><MousePointer2 size={12}/>Drag to pan · scroll to zoom</span><button onClick={fit} title="Fit view (0 / Z)"><Maximize2 size={14}/>Fit view</button></div>
  </div>;
}
