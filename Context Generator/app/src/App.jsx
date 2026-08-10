import React, { useEffect } from 'react';
import { useStore } from './store/useStore';
import { SceneViewer } from './components/SceneViewer';
import { SiteInfoCard } from './components/SiteInfoCard';
import { FilterBar } from './components/FilterBar';
import { CarouselNav } from './components/CarouselNav';
import { BottomBar } from './components/BottomBar';
import './App.css';

export function App() {
  const setDataset = useStore((s) => s.setDataset);

  useEffect(() => {
    fetch('/dataset/master_urban_dataset.json')
      .then((res) => {
        if (!res.ok) {
          throw new Error(`Dataset fetch returned ${res.status}`);
        }
        return res.json();
      })
      .then((data) => {
        if (Array.isArray(data)) {
          setDataset(data);
        }
      })
      .catch((err) => {
        console.error('Error loading master_urban_dataset.json:', err);
      });
  }, [setDataset]);

  return (
    <div className="app-root">
      <SceneViewer />
      <SiteInfoCard />
      <FilterBar />
      <CarouselNav />
      <BottomBar />
    </div>
  );
}

export default App;
