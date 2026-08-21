import React, { useEffect } from 'react';
import { useStore } from './store/useStore';
import { TopHud } from './components/TopHud';
import { ThreeViewer } from './components/ThreeViewer';
import { PlanCanvas2D } from './components/PlanCanvas2D';
import { BottomDock } from './components/BottomDock';
import { SettingsDrawer } from './components/SettingsDrawer';
import { ResetModal } from './components/ResetModal';
import { CustomSiteModal } from './components/CustomSiteModal';
import './App.css';

export function App() {
  const initWebSocket = useStore((s) => s.initWebSocket);
  const toggleTraining = useStore((s) => s.toggleTraining);
  const requestNewSite = useStore((s) => s.requestNewSite);
  const toggleMerging = useStore((s) => s.toggleMerging);
  const setResetConfirmOpen = useStore((s) => s.setResetConfirmOpen);
  const saveCheckpoint = useStore((s) => s.saveCheckpoint);
  const mode = useStore((s) => s.mode);
  const maximizedPane = useStore((s) => s.maximizedPane);
  const setDeveloperOpen = useStore((s) => s.setDeveloperOpen);
  const developerOpen = useStore((s) => s.developerOpen);

  // Initialize Connection
  useEffect(() => {
    initWebSocket();
  }, [initWebSocket]);

  // Global Keyboard Shortcuts
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') {
        return;
      }

      if (e.code === 'Space') {
        e.preventDefault();
        toggleTraining();
      } else if (e.code === 'KeyN') {
        e.preventDefault();
        requestNewSite();
      } else if (e.code === 'KeyM') {
        e.preventDefault();
        toggleMerging();
      } else if (e.code === 'KeyR' && mode === 'training') {
        e.preventDefault();
        setResetConfirmOpen(true);
      } else if (e.code === 'KeyS' && mode === 'training') {
        e.preventDefault();
        saveCheckpoint();
      } else if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.code === 'KeyD') {
        e.preventDefault();
        setDeveloperOpen(!developerOpen);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [toggleTraining, requestNewSite, toggleMerging, setResetConfirmOpen, saveCheckpoint, mode, developerOpen, setDeveloperOpen]);

  return (
    <div className="app-shell">
      <TopHud />

      <main className="stage">
        <div className={`stage-split-container ${maximizedPane ? `maximized-${maximizedPane}` : ''}`}>
          {maximizedPane !== 'right' && <ThreeViewer />}
          {maximizedPane !== 'left' && <PlanCanvas2D />}
        </div>
      </main>

      <BottomDock />
      <SettingsDrawer />
      <ResetModal />
      <CustomSiteModal />
    </div>
  );
}

export default App;
