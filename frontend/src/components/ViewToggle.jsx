import React from 'react';
import { useStore } from '../store/useStore';
export function ViewToggle() {
  const mode=useStore((s)=>s.viewMode), setMode=useStore((s)=>s.setViewMode);
  return <div className="view-mode-pill glass-card top-toolbar-group">
    <button className={`view-btn ${mode==='axonometric'?'active':''}`} onClick={()=>setMode('axonometric')}>Axonometric</button>
    <button className={`view-btn ${mode==='perspective'?'active':''}`} onClick={()=>setMode('perspective')}>Perspective</button>
    <button className="view-btn" onClick={()=>window.dispatchEvent(new CustomEvent('reset_views'))}>Fit view</button>
  </div>;
}
