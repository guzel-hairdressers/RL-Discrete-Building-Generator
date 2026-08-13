import React, { useEffect } from 'react';
import { useStore } from './store/useStore';
import { SceneViewer } from './components/SceneViewer';
import { SiteInfoCard } from './components/SiteInfoCard';
import { FilterBar } from './components/FilterBar';
import { CarouselNav } from './components/CarouselNav';
import { BottomBar } from './components/BottomBar';
import { CustomSiteModal } from './components/CustomSiteModal';
import './App.css';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('App ErrorBoundary caught error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: '20px', color: '#0f172a', fontFamily: 'sans-serif' }}>
          <h2>Application Error</h2>
          <p>{this.state.error?.toString()}</p>
          <button
            onClick={() => {
              this.setState({ hasError: false });
              window.location.reload();
            }}
            style={{ padding: '8px 16px', marginTop: '10px', cursor: 'pointer' }}
          >
            Reload App
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export function App() {
  const setDataset = useStore((s) => s.setDataset);

  useEffect(() => {
    Promise.all([
      fetch('/data/master_urban_dataset.json').then((r) => (r.ok ? r.json() : [])).catch(() => []),
      fetch('/data/custom_sites_dataset.json').then((r) => (r.ok ? r.json() : [])).catch(() => []),
    ]).then(([masterData, customData]) => {
      const masterArr = Array.isArray(masterData) ? masterData : [];
      const customArr = Array.isArray(customData) ? customData : [];
      setDataset([...customArr, ...masterArr]);
    });
  }, [setDataset]);

  return (
    <ErrorBoundary>
      <div className="app-root">
        <SceneViewer />
        <SiteInfoCard />
        <FilterBar />
        <CarouselNav />
        <BottomBar />
        <CustomSiteModal />
      </div>
    </ErrorBoundary>
  );
}

export default App;
