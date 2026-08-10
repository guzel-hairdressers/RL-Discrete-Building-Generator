import { create } from 'zustand';

// Tier Range Definitions (XS, S, M, L, XL)
export const TIER_RANGES = {
  XS: [150, 600],
  S:  [600, 1200],
  M:  [1200, 2500],
  L:  [2500, 4500],
  XL: [4000, 10000],
};

const DEFAULT_FILTERS = {
  city: 'prs', // Paris preselected by default as requested
  activeTier: 'S', // S Tier preselected by default
  minArea: 600,
  maxArea: 1200,
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
        updated.activeTier = null; // Clear tier button highlight when slider moves customly
      }
      return { filters: updated };
    });
    get().applyFilters();
  },

  // Select small Tier preset button (XS, S, M, L, XL)
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

  // Reset all filters to default state (Paris preselected, S tier active)
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
