import React from 'react';
import { useStore } from '../store/useStore';

const CITY_COORDS = {
  prs: { lat: 48.8656, lon: 2.3364 },
  nyc: { lat: 40.7580, lon: -73.9855 },
  bcn: { lat: 41.3917, lon: 2.1649 },
  chi: { lat: 41.8781, lon: -87.6298 },
  tokyo: { lat: 35.6938, lon: 139.7034 },
  ldn: { lat: 51.5128, lon: -0.0918 },
  hk: { lat: 22.2819, lon: 114.1581 },
  sgp: { lat: 1.2839, lon: 103.8515 },
};

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

  const cityCoord = CITY_COORDS[site.city_code] || { lat: 48.8656, lon: 2.3364 };
  const latVal = site.lat ?? cityCoord.lat;
  const lonVal = site.lon ?? cityCoord.lon;

  return (
    <div id="site-info-card" className="glass-card">
      <div id="site-city-title">{site.city_name || site.city_code.toUpperCase()}</div>
      <div id="site-coords">
        Lat: {latVal.toFixed(4)}, Lon: {lonVal.toFixed(4)}
      </div>
      <div className="info-grid">
        <div className="info-item full-width">
          <span className="info-label">SITE AREA</span>
          <span className="info-val">
            {site.site_area_m2?.toFixed(1) || '--'} m² ({site.area_tier})
          </span>
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
