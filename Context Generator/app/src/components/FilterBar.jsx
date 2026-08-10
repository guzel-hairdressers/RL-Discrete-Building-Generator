import React from 'react';
import { useStore } from '../store/useStore';

export const FilterBar = () => {
  const filters = useStore((s) => s.filters);
  const setFilter = useStore((s) => s.setFilter);
  const selectTier = useStore((s) => s.selectTier);
  const resetFilters = useStore((s) => s.resetFilters);

  return (
    <div id="filter-bar" className="glass-bar wide-bar">
      
      {/* 1. City Section (Far Left, Paris preselected by default) */}
      <div className="filter-group compact">
        <span className="group-title baseline-title">City</span>
        <select
          id="select-city"
          className="custom-select"
          value={filters.city}
          onChange={(e) => setFilter('city', e.target.value)}
        >
          <option value="ALL">All Cities</option>
          <option value="prs">Paris</option>
          <option value="nyc">NYC</option>
          <option value="tokyo">Tokyo</option>
          <option value="bcn">Barcelona</option>
          <option value="ldn">London</option>
          <option value="chi">Chicago</option>
          <option value="hk">Hong Kong</option>
          <option value="sgp">Singapore</option>
        </select>
      </div>

      {/* 2. Site Area Section (Center, Right-Aligned Small Tier Buttons, Numbers Below Slider) */}
      <div className="filter-group flex-grow">
        <div className="group-header">
          <span className="group-title baseline-title">Site Area</span>
          <div className="tier-buttons right-aligned">
            {['XS', 'S', 'M', 'L', 'XL'].map((t) => (
              <button
                key={t}
                className={`tier-btn ${filters.activeTier === t ? 'active' : ''}`}
                onClick={() => selectTier(t)}
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        <div className="dual-range-container">
          <input
            type="range"
            min="150"
            max="4500"
            step="25"
            value={filters.minArea}
            onChange={(e) => setFilter('minArea', Math.min(parseInt(e.target.value), filters.maxArea))}
          />
          <input
            type="range"
            min="150"
            max="4500"
            step="25"
            value={filters.maxArea}
            onChange={(e) => setFilter('maxArea', Math.max(parseInt(e.target.value), filters.minArea))}
          />
          <div className="range-track"></div>
        </div>

        {/* Numerical Range Readout BELOW Slider */}
        <div className="range-values-below">
          {filters.minArea} m² - {filters.maxArea} m²
        </div>
      </div>

      {/* 3. Context Height Section (Right, Numbers Below Slider) */}
      <div className="filter-group flex-grow">
        <div className="group-header">
          <span className="group-title baseline-title">Context Height</span>
        </div>

        <div className="dual-range-container">
          <input
            type="range"
            min="10"
            max="300"
            step="5"
            value={filters.minHeight}
            onChange={(e) => setFilter('minHeight', Math.min(parseInt(e.target.value), filters.maxHeight))}
          />
          <input
            type="range"
            min="10"
            max="300"
            step="5"
            value={filters.maxHeight}
            onChange={(e) => setFilter('maxHeight', Math.max(parseInt(e.target.value), filters.minHeight))}
          />
          <div className="range-track"></div>
        </div>

        {/* Numerical Height Readout BELOW Slider */}
        <div className="range-values-below">
          {filters.minHeight}m - {filters.maxHeight}m
        </div>
      </div>

      {/* 4. Clean Reset Button (Far Right) */}
      <button className="btn-secondary" onClick={resetFilters} title="Reset All Filters">
        Reset
      </button>

    </div>
  );
};
