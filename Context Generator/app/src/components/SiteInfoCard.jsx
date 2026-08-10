import React from 'react';
import { useStore } from '../store/useStore';

export const SiteInfoCard = () => {
  const filteredSites = useStore((s) => s.filteredSites);
  const activeSiteIndex = useStore((s) => s.activeSiteIndex);
  
  const site = filteredSites[activeSiteIndex];

  if (!site) {
    return (
      <div id="site-info-card" className="glass-card">
        <div id="site-city-title">NO MATCHING SITES</div>
        <div id="site-coords">Adjust filters to view sites</div>
      </div>
    );
  }

  const avgStoreys = Math.round((site.avg_height_m || 0) / 3.2);
  const maxStoreys = Math.round((site.max_height_m || 0) / 3.2);

  return (
    <div id="site-info-card" className="glass-card">
      <div id="site-city-title">{site.city_name || site.city_code.toUpperCase()}</div>
      <div id="site-coords">
        Lat: {site.lat?.toFixed(4) || '--'}, Lon: {site.lon?.toFixed(4) || '--'}
      </div>
      <div className="info-grid">
        <div className="info-item">
          <span className="info-label">SITE AREA</span>
          <span className="info-val">{site.site_area_m2?.toFixed(1) || '--'} m²</span>
        </div>
        <div className="info-item">
          <span className="info-label">AREA TIER</span>
          <span className="info-val">{site.area_tier} Tier</span>
        </div>
        <div className="info-item">
          <span className="info-label">FAR</span>
          <span className="info-val">{site.far?.toFixed(2) || '2.50'}</span>
        </div>
        <div className="info-item">
          <span className="info-label">BUILDINGS</span>
          <span className="info-val">{site.building_count || '--'}</span>
        </div>
        <div className="info-item full-width">
          <span className="info-label">CONTEXT HEIGHT</span>
          <span className="info-val">
            {site.avg_height_m?.toFixed(1) || 0}m | {site.max_height_m?.toFixed(1) || 0}m
          </span>
        </div>
        <div className="info-item full-width">
          <span className="info-label">CONTEXT STOREYS</span>
          <span className="info-val">
            {avgStoreys} | {maxStoreys}
          </span>
        </div>
      </div>
    </div>
  );
};
