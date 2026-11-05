import React, { useRef } from 'react';
import { Play, Pause, Sparkles, ChevronDown, Settings2, Activity, Download, Upload, RotateCcw } from 'lucide-react';
import { useStore } from '../store/useStore';

export function BottomControlDeck() {
  const s = useStore();
  const file = useRef(null);
  const unavailable = !s.connected || !s.hasSite || s.pendingSite || s.awaitingMode || s.evaluationInFlight;
  const load = (event) => {
    const selected = event.target.files?.[0];
    if (!selected) return;
    const reader = new FileReader();
    reader.onload = () => s.loadCheckpoint(String(reader.result).split(',')[1]);
    reader.readAsDataURL(selected); event.target.value = '';
  };
  return <header className="lab-header">
    <a className="lab-brand" href="#" aria-label="Module Lab home"><span className="brand-mark">M<span>╱</span>L</span><span>Module Lab<small>Spatial design studio · v0.10.0</small></span></a>
    <div className="run-state"><i className={s.connected ? 'connected' : ''} /><span>{s.mode === 'training' ? 'Training' : 'Inference'}<small>{s.trainingWanted ? 'Running' : s.pendingSite ? 'Preparing site' : s.phase === 'complete' ? 'Complete' : 'Paused'} · {s.device}</small></span></div>
    <nav className="action-bar" aria-label="Run controls">
      <button className="primary-action" disabled={unavailable && !s.trainingWanted} onClick={s.trainingWanted ? s.pauseExecution : s.startTraining}>{s.trainingWanted ? <Pause size={15}/> : <Play size={15}/>} {s.trainingWanted ? 'Pause' : 'Train'}<kbd>␣</kbd></button>
      <button disabled={unavailable || s.trainingWanted || s.stepInFlight} onClick={s.startInference}><Sparkles size={15}/>Generate one layout</button>
      <details className="checkpoint-menu"><summary>Checkpoint <ChevronDown size={13}/></summary><div className="menu-content">
        <button disabled={!s.connected} onClick={s.saveCheckpoint}><Download size={14}/>Save weights</button>
        <button disabled={unavailable || s.trainingWanted} onClick={() => file.current.click()}><Upload size={14}/>Load weights…</button>
        <button className="danger-text" disabled={unavailable} onClick={() => s.setResetConfirmOpen(true)}><RotateCcw size={14}/>Reset weights…</button>
      </div></details>
      <input ref={file} type="file" accept=".pt" hidden onChange={load}/>
      <button className={s.activeBottomDrawer === 'settings' ? 'active' : ''} onClick={() => s.setActiveBottomDrawer('settings')} aria-label="Configuration"><Settings2 size={17}/><span className="optional-label">Configure</span></button>
      <button className={s.activeBottomDrawer === 'diagnostics' ? 'active' : ''} onClick={() => s.setActiveBottomDrawer('diagnostics')} aria-label="Diagnostics"><Activity size={17}/></button>
    </nav>
  </header>;
}
