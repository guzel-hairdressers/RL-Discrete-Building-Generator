import React, { useEffect } from 'react';
import { useStore } from './store/useStore';
import { ThreeViewer } from './components/ThreeViewer';
import { PlanCanvas2D } from './components/PlanCanvas2D';
import { BottomControlDeck } from './components/BottomControlDeck';
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
  const setActiveBottomDrawer = useStore((s) => s.setActiveBottomDrawer);
  const activeBottomDrawer = useStore((s) => s.activeBottomDrawer);

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

      const isCmdOrCtrl = e.metaKey || e.ctrlKey;

      // Ctrl/Cmd+Shift+D for Diagnostics
      if (isCmdOrCtrl && e.shiftKey && e.code === 'KeyD') {
        e.preventDefault();
        setActiveBottomDrawer(activeBottomDrawer === 'diagnostics' ? null : 'diagnostics');
        return;
      }

      // If Cmd, Ctrl, or Alt is held, allow standard browser actions (Reload Cmd+R, Hard Reload Cmd+Shift+R, Save Cmd+S, etc.)
      if (isCmdOrCtrl || e.altKey) {
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
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [toggleTraining, requestNewSite, toggleMerging, setResetConfirmOpen, saveCheckpoint, mode, activeBottomDrawer, setActiveBottomDrawer]);

  return (
    <div className="app-shell">
      <main className="stage">
        <div className={`stage-split-container ${maximizedPane ? `maximized-${maximizedPane}` : ''}`}>
          {maximizedPane !== 'right' && <ThreeViewer />}
          {maximizedPane !== 'left' && <PlanCanvas2D />}
        </div>
      </main>

      {/* Unified Bottom Control Deck (Filters, Action Split Button, Metrics HUD, Reward Trend, Expandable Drawers) */}
      <BottomControlDeck />

      <ResetModal />
      <CustomSiteModal />
    </div>
  );
}

export default App;
