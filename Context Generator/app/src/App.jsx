import React, { useEffect } from 'react';
import { useStore } from './store/useStore';
import { SceneViewer } from './components/SceneViewer';
import { SiteInfoCard } from './components/SiteInfoCard';
import { FilterBar } from './components/FilterBar';
import { CarouselNav } from './components/CarouselNav';
import { BottomBar } from './components/BottomBar';
import { CustomSiteModal } from './components/CustomSiteModal';
import './App.css';

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
    <div className="app-root">
      <SceneViewer />
      <SiteInfoCard />
      <FilterBar />
      <CarouselNav />
      <BottomBar />
      <CustomSiteModal />
    </div>
  );
}

export default App;
