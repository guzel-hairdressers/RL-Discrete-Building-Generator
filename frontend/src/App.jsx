import React, { useEffect, useState } from 'react';
import { ArrowLeft, ArrowRight, Layers3, Box, ScanLine, Network, Route, Eye } from 'lucide-react';
import { useStore } from './store/useStore';
import { ThreeViewer } from './components/ThreeViewer';
import { PlanCanvas2D } from './components/PlanCanvas2D';
import { BottomControlDeck } from './components/BottomControlDeck';
import { OutcomeStrip, ModulePalette, ConfigurationDrawer } from './components/WorkspacePanels';
import { DiagnosticsDrawer } from './components/DiagnosticsDrawer';
import { RewardTrendChart } from './components/RewardTrendChart';
import { ResetModal } from './components/ResetModal';
import { CustomSiteModal } from './components/CustomSiteModal';
import './App.css';
import './workspace.css';
import './editorial.css';
export function App() {
  const s=useStore();
  const [hasOpened3D, setHasOpened3D] = useState(false);
  useEffect(() => { if (s.show3D) setHasOpened3D(true); }, [s.show3D]);
  useEffect(()=>{s.initWebSocket();},[s.initWebSocket]);
  useEffect(()=>{
    const keyboard=(e)=>{
      if(e.key==='Escape'){s.setActiveBottomDrawer(null);s.setResetConfirmOpen(false);s.setCustomModalOpen(false);return;}
      if(e.target.closest('input,select,textarea,[contenteditable="true"]'))return;
      if((e.ctrlKey||e.metaKey)&&e.shiftKey&&e.code==='KeyD'){e.preventDefault();s.setActiveBottomDrawer('diagnostics');return;}
      if(s.activeBottomDrawer||s.resetConfirmOpen||s.customModalOpen||e.ctrlKey||e.metaKey||e.altKey||e.repeat)return;
      if(e.code==='Space'&&e.target.closest('button,summary,a'))return;
      if(e.code==='Space'){e.preventDefault();s.toggleTraining();}
      if(['0','z','Z'].includes(e.key))window.dispatchEvent(new CustomEvent('reset_views'));
      if(e.key.toLowerCase()==='r')s.setResetConfirmOpen(true);
      if(e.key.toLowerCase()==='s')s.saveCheckpoint();
      if(e.key.toLowerCase()==='n')s.requestNewSite();
      if(e.key==='ArrowLeft'&&s.settings.boundaryType==='real')s.navigateCarousel(-1);
      if(e.key==='ArrowRight'&&s.settings.boundaryType==='real')s.navigateCarousel(1);
    };
    window.addEventListener('keydown',keyboard);return()=>window.removeEventListener('keydown',keyboard);
  },[s]);
  const site=s.contextData;
  return <div className="app-shell lab-workspace"><BottomControlDeck/><OutcomeStrip/>
    <main className="workspace-layout"><section className="drawing-region">
      <div className="workspace-title"><div><span className="eyebrow">Workspace / {s.mode==='training'?'Training':'Generate'}</span><h1>{s.settings.boundaryType==='real'?(site?.city_name||site?.city_code||'Urban site study'):'Procedural site study'}<span>{s.boundaries.length||'—'} floors</span></h1></div><div className="site-navigation"><button aria-label="Previous site" disabled={s.pendingSite||s.settings.boundaryType!=='real'} onClick={()=>s.navigateCarousel(-1)}><ArrowLeft size={15}/></button><button disabled={s.pendingSite} onClick={s.requestNewSite}>Next site <ArrowRight size={15}/></button></div></div>
      <div className="workspace-toolbar"><label className="floor-select"><Layers3 size={14}/><select aria-label="Displayed floor" value={s.selectedFloor} onChange={(e)=>s.setSelectedFloor(e.target.value)}><option value="all">All floors</option>{s.boundaries.map((_,i)=><option key={i} value={i}>Floor {i+1}</option>)}</select></label><div className="layer-controls"><button className={s.showGraph?'active':''} aria-pressed={s.showGraph} onClick={()=>s.setShowGraph(!s.showGraph)}><Network size={14}/>Graph</button><button className={s.showAccess?'active':''} aria-pressed={s.showAccess} onClick={()=>s.setShowAccess(!s.showAccess)} title="Only explicit usable-access edges establish door connections"><Route size={14}/>Access</button></div><div className="view-controls"><button aria-pressed={s.show3D} className={s.show3D?'active':''} onClick={()=>s.setShow3D(!s.show3D)}><Box size={14}/>{s.show3D?'Hide 3D':'Show 3D'}</button><button disabled={s.trainingWanted||s.pendingSite||s.evaluationInFlight||!s.hasSite} onClick={s.requestEvaluation}><ScanLine size={14}/>{s.evaluationInFlight?'Checking…':'Check geometry'}</button></div></div>
      <div className={`drawing-surfaces ${s.show3D?'with-context':''}`}><div className="plan-container"><PlanCanvas2D/></div><div className={`context-container ${s.show3D?'':'context-hidden'}`}>{(s.show3D || hasOpened3D) && <ThreeViewer/>}</div></div>
      <div className="workspace-status" role="status"><span><i className={s.trainingWanted?'running-dot':''}/>{s.statusMessage}</span><span>Episode {s.episode} · batch {s.step}<b>Batch ≠ module count</b></span></div><RewardTrendChart/>
    </section><ModulePalette/></main>
    <footer className="workspace-footer"><span>Module Lab · Research preview</span><span><Eye size={12}/>Environmental performance unmeasured</span><span>{s.connected?'Optimizer connected':'Optimizer disconnected'}</span></footer>
    {s.activeBottomDrawer==='settings'&&<ConfigurationDrawer/>}{s.activeBottomDrawer==='diagnostics'&&<DiagnosticsDrawer onClose={()=>s.setActiveBottomDrawer(null)}/>}<ResetModal/><CustomSiteModal/>
  </div>;
}
export default App;
