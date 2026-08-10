import { create } from 'zustand';

// Tier Range Definitions (ANY, XS, S, M, L, XL)
export const TIER_RANGES = {
  ANY: [150, 10000],
  XS:  [150, 600],
  S:   [600, 1200],
  M:   [1200, 2500],
  L:   [2500, 4000],
  XL:  [4000, 10000],
};

// Convert percentage (0 to 100) -> Area m² (150 to 10000 m²) across 5 equal 20% tier zones
export function percentToArea(p) {
  p = Math.max(0, Math.min(100, p));
  if (p <= 20) {
    return Math.round(150 + (p / 20) * (600 - 150));
  } else if (p <= 40) {
    return Math.round(600 + ((p - 20) / 20) * (1200 - 600));
  } else if (p <= 60) {
    return Math.round(1200 + ((p - 40) / 20) * (2500 - 1200));
  } else if (p <= 80) {
    return Math.round(2500 + ((p - 60) / 20) * (4000 - 2500));
  } else {
    return Math.round(4000 + ((p - 80) / 20) * (10000 - 4000));
  }
}

// Convert Area m² (150 to 10000 m²) -> percentage (0 to 100) across 5 equal 20% tier zones
export function areaToPercent(a) {
  a = Math.max(150, Math.min(10000, a));
  if (a <= 600) {
    return 0 + ((a - 150) / (600 - 150)) * 20;
  } else if (a <= 1200) {
    return 20 + ((a - 600) / (1200 - 600)) * 20;
  } else if (a <= 2500) {
    return 40 + ((a - 1200) / (2500 - 1200)) * 20;
  } else if (a <= 4000) {
    return 60 + ((a - 2500) / (4000 - 2500)) * 20;
  } else {
    return 80 + ((a - 4000) / (10000 - 4000)) * 20;
  }
}

const DEFAULT_FILTERS = {
  city: 'ALL', // "ALL" CITIES preselected by default as requested
  activeTier: 'ANY', // "ANY" Tier preselected by default as requested
  minArea: 150,
  maxArea: 10000,
  minHeight: 10,
  maxHeight: 300,
};

export const useStore = create((set, get) => ({
  allSites: [],
  filteredSites: [],
  activeSiteIndex: 0,
  viewMode: 'axonometric', // 'axonometric' | 'perspective'
  filters: { ...DEFAULT_FILTERS },

  // Set initial loaded dataset
  setDataset: (sites) => {
    set({ allSites: sites });
    get().applyFilters();
  },

  // Update specific filter property
  setFilter: (key, value) => {
    set((state) => {
      const updated = { ...state.filters, [key]: value };
      if (key === 'minArea' || key === 'maxArea') {
        // Auto-check if current min/max match any tier range
        const minA = updated.minArea;
        const maxA = updated.maxArea;
        let matchedTier = null;
        for (const [tierKey, [tMin, tMax]] of Object.entries(TIER_RANGES)) {
          if (minA === tMin && maxA === tMax) {
            matchedTier = tierKey;
            break;
          }
        }
        updated.activeTier = matchedTier;
      }
      return { filters: updated };
    });
    get().applyFilters();
  },

  // Select small Tier preset button (ANY, XS, S, M, L, XL)
  selectTier: (tier) => {
    const range = TIER_RANGES[tier];
    if (range) {
      set((state) => ({
        filters: {
          ...state.filters,
          activeTier: tier,
          minArea: range[0],
          maxArea: range[1],
        },
      }));
      get().applyFilters();
    }
  },

  // Reset all filters to default state (All cities, Any tier active)
  resetFilters: () => {
    set({ filters: { ...DEFAULT_FILTERS } });
    get().applyFilters();
  },

  // Apply client-side filtering over master_urban_dataset.json (<0.1ms)
  applyFilters: () => {
    const { allSites, filters } = get();
    const filtered = allSites.filter((site) => {
      // City Filter
      if (filters.city !== 'ALL' && site.city_code !== filters.city) return false;

      // Area Filter
      if (site.site_area_m2 < filters.minArea || site.site_area_m2 > filters.maxArea) return false;

      // Height Filter
      const avgH = site.avg_height_m || 0;
      if (avgH < filters.minHeight || avgH > filters.maxHeight) return false;

      return true;
    });

    set({
      filteredSites: filtered,
      activeSiteIndex: 0,
    });
  },

  // Navigate Carousel (Next/Prev)
  navigateCarousel: (delta) => {
    const { filteredSites, activeSiteIndex } = get();
    if (filteredSites.length === 0) return;
    const nextIndex = (activeSiteIndex + delta + filteredSites.length) % filteredSites.length;
    set({ activeSiteIndex: nextIndex });
  },

  // Pick Random Site (Forced to pick a site that is NOT the current active one; does nothing if <= 1 site)
  pickRandomSite: () => {
    const { filteredSites, activeSiteIndex } = get();
    if (filteredSites.length <= 1) return;
    
    // Uniform random pick among all indices excluding activeSiteIndex
    let randomIndex = Math.floor(Math.random() * (filteredSites.length - 1));
    if (randomIndex >= activeSiteIndex) {
      randomIndex += 1;
    }
    
    set({ activeSiteIndex: randomIndex });
  },

  // Toggle Camera View Mode
  setViewMode: (mode) => set({ viewMode: mode }),
}));
