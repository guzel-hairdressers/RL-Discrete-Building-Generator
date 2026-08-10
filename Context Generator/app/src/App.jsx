import React, { useEffect } from 'react';
import { useStore } from './store/useStore';
import { ThreeCanvas } from './components/ThreeCanvas';
import { FilterBar } from './components/FilterBar';
import { SiteInfoCard } from './components/SiteInfoCard';
import { ViewToggle } from './components/ViewToggle';
import { CarouselNav } from './components/CarouselNav';
import { BottomBar } from './components/BottomBar';
import './App.css';

export function App() {
  const setDataset = useStore((s) => s.setDataset);

  useEffect(() => {
    // Fetch master_urban_dataset.json on mount
    fetch('/dataset/master_urban_dataset.json')
      .then((res) => {
        if (!res.ok) {
          // Fallback if serving from subfolder
          return fetch('../dataset/master_urban_dataset.json');
        }
        return res.json();
      })
      .then((data) => {
        setDataset(data);
      })
      .catch((err) => {
        console.error('Error loading master_urban_dataset.json:', err);
      });
  }, [setDataset]);

  return (
    <div className="app-root">
      <ThreeCanvas />
      <SiteInfoCard />
      <FilterBar />
      <ViewToggle />
      <CarouselNav />
      <BottomBar />
    </div>
  );
}

export default App;
