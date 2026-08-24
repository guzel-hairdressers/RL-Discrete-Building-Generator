import React, { useEffect } from 'react';
import { useStore } from './store/useStore';
import { ThreeViewer } from './components/ThreeViewer';
import { PlanCanvas2D } from './components/PlanCanvas2D';
import { BottomControlDeck } from './components/BottomControlDeck';
import { ResetModal } from './components/ResetModal';
import { CustomSiteModal } from './components/CustomSiteModal';
import { CarouselNav } from './components/CarouselNav';
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

  // Initialize Connection and optional autotrain for automated verification
  useEffect(() => {
    initWebSocket();
    const params = new URLSearchParams(window.location.search);
    if (params.get('autotrain') === '1') {
      const timer = setTimeout(() => {
        toggleTraining();
      }, 1200);
      return () => clearTimeout(timer);
    }
  }, [initWebSocket, toggleTraining]);

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

      // If Cmd, Ctrl, or Alt is held, allow standard browser actions (Reload Cmd+R, Hard Reload Cmd+Shift+R, Save Cmd+S, DevTools, etc.)
      if (isCmdOrCtrl || e.altKey) {
        return;
      }

      // Space: Toggle Training / Inference
      if (e.code === 'Space') {
        e.preventDefault();
        toggleTraining();
        return;
      }

      // 'r' or 'R': Reset Weights (Single key press without Cmd/Ctrl)
      if (e.key === 'r' || e.key === 'R') {
        e.preventDefault();
        setResetConfirmOpen(true);
        return;
      }

      // 's' or 'S': Save Weights
      if (e.key === 's' || e.key === 'S') {
        e.preventDefault();
        saveCheckpoint();
        return;
      }

      // 'm' or 'M': Toggle Room Merging (BPE)
      if (e.key === 'm' || e.key === 'M') {
        e.preventDefault();
        toggleMerging();
        return;
      }

      // 'n' or 'N': Next Site Request
      if (e.key === 'n' || e.key === 'N') {
        e.preventDefault();
        requestNewSite();
        return;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [toggleTraining, requestNewSite, toggleMerging, setResetConfirmOpen, saveCheckpoint, mode, activeBottomDrawer, setActiveBottomDrawer]);

  return (
    <div className="app-shell">
      <main className="stage">
        <div className={`stage-split-container ${maximizedPane ? `maximized-${maximizedPane}` : ''}`}>
          <ThreeViewer />
          <div className="stage-center-divider" />
          <PlanCanvas2D />
        </div>
        <CarouselNav />
      </main>

      {/* Unified Bottom Control Deck (Filters, Action Split Button, Metrics HUD, Reward Trend, Expandable Drawers) */}
      <BottomControlDeck />

      <ResetModal />
      <CustomSiteModal />
    </div>
  );
}

export default App;
