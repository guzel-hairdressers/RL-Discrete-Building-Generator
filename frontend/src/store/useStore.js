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

export function percentToArea(p) {
  p = Math.max(0, Math.min(100, p));
  if (p <= 20) return Math.round(150 + (p / 20) * (600 - 150));
  if (p <= 40) return Math.round(600 + ((p - 20) / 20) * (1200 - 600));
  if (p <= 60) return Math.round(1200 + ((p - 40) / 20) * (2500 - 1200));
  if (p <= 80) return Math.round(2500 + ((p - 60) / 20) * (4000 - 2500));
  return Math.round(4000 + ((p - 80) / 20) * (10000 - 4000));
}

export function areaToPercent(a) {
  a = Math.max(150, Math.min(10000, a));
  if (a <= 600) return 0 + ((a - 150) / (600 - 150)) * 20;
  if (a <= 1200) return 20 + ((a - 600) / (1200 - 600)) * 20;
  if (a <= 2500) return 40 + ((a - 1200) / (2500 - 1200)) * 20;
  if (a <= 4000) return 60 + ((a - 2500) / (4000 - 2500)) * 20;
  return 80 + ((a - 4000) / (10000 - 4000)) * 20;
}

export const DEFAULT_SETTINGS = {
  boundaryType: 'real',
  siteAreaTier: 'ANY',
  city: 'ALL',
  atriumPolicy: 'none',
  singleFloor: false,
  publicMode: false,
  parallelEnvironments: 9,
  maxModules: 130,
  learningRate: 0.003,
  minEdge: 3.0,
  maxEdge: 9.0,
  dictCap: 10,
  angleStep: 15.0,
  coreSpacing: 8.0,
  travelLimit: 12,
  maxRoomHops: 3,
  allowCorridors: false,
  allowStop: true,
  lookaheadSteps: 3,
};

const DEFAULT_FILTERS = {
  city: 'ALL',
  activeTier: 'ANY',
  minArea: 150,
  maxArea: 10000,
  minHeight: 10,
  maxHeight: 300,
};

export const useStore = create((set, get) => ({
  // WebSocket Connection
  socket: null,
  connected: false,
  connectionState: 'connecting',
  device: 'CPU',
  statusMessage: 'Live protocol idle',

  // Optimizer Mode & Phase
  mode: 'training',
  phase: 'paused',
  trainingWanted: false,
  autoGenerate: true,
  disableMerging: false,

  // Run Telemetry
  generationId: 0,
  episode: 0,
  step: 0,
  bestScore: -40.0,
  scoreHistory: [],
  metrics: {
    score: -40.0,
    fillRatio: 0,
    rentableRatio: 0,
    daylightRatio: 0,
    reuseRatio: 0,
    envelopeEfficiency: 0,
  },
  diagnostics: {},

  // Real Sites Urban Dataset (Context Generator Engine)
  allSites: [],
  filteredSites: [],
  activeSiteIndex: 0,
  customModalOpen: false,
  filters: { ...DEFAULT_FILTERS },

  // Site & Geometry State
  hasSite: false,
  boundaries: [],
  totalSiteArea: 0,
  individualPlacementsList: [],
  currentMergedPlacements: [],
  dictionary: [],
  mergedDictionary: [],
  contextData: null,

  // 3D & 2D View Controls
  viewMode: 'axonometric',
  maximizedPane: null,
  hoveredModuleId: null,

  // Settings & Panels
  settings: { ...DEFAULT_SETTINGS },
  settingsOpen: false,
  developerOpen: false,
  resetConfirmOpen: false,

  // Setters
  setCustomModalOpen: (open) => set({ customModalOpen: open }),
  setMode: (newMode) => {
    set({ mode: newMode });
    get().sendCommand({ cmd: 'setMode', mode: newMode });
  },
  setSettingsOpen: (open) => set({ settingsOpen: open }),
  setDeveloperOpen: (open) => set({ developerOpen: open }),
  setResetConfirmOpen: (open) => set({ resetConfirmOpen: open }),
  setViewMode: (mode) => set({ viewMode: mode }),
  setMaximizedPane: (pane) => set((s) => ({ maximizedPane: s.maximizedPane === pane ? null : pane })),
  setHoveredModuleId: (id) => set({ hoveredModuleId: id }),

  // Load Context Generator Urban Dataset
  loadDatasets: async () => {
    try {
      let master = [];
      let custom = [];
      try {
        const r1 = await fetch(`/data/master_urban_dataset.json?t=${Date.now()}`);
        if (r1.ok) master = await r1.json();
      } catch (e) {}

      try {
        const r2 = await fetch(`/data/custom_sites_dataset.json?t=${Date.now()}`);
        if (r2.ok) {
          const rawCustom = await r2.json();
          if (Array.isArray(rawCustom)) {
            custom = rawCustom.map((s) => ({
              ...s,
              is_custom: true,
              render_html: s.render_html
                ? (s.render_html.includes('?') ? s.render_html : `${s.render_html}?t=${Date.now()}`)
                : `sites/${s.site_id}.html?t=${Date.now()}`,
            }));
          }
        }
      } catch (e) {}

      const combined = [...custom, ...master];
      set({ allSites: combined });
      get().applyFilters();
    } catch (err) {
      console.warn('Dataset loading warning:', err);
    }
  },

  // Add Custom Site (From interactive map or drawing)
  addCustomSite: (customSite) => {
    const siteWithCacheBust = {
      ...customSite,
      is_custom: true,
      render_html: customSite.render_html
        ? (customSite.render_html.includes('?') ? customSite.render_html : `${customSite.render_html}?t=${Date.now()}`)
        : `sites/${customSite.site_id}.html?t=${Date.now()}`,
    };

    set((state) => {
      const exists = state.allSites.some((s) => s.site_id === customSite.site_id);
      const newSites = exists
        ? state.allSites.map((s) => (s.site_id === customSite.site_id ? siteWithCacheBust : s))
        : [siteWithCacheBust, ...state.allSites];
      return {
        allSites: newSites,
        filters: { ...DEFAULT_FILTERS },
      };
    });

    get().applyFilters();
    const filtered = get().filteredSites;
    const idx = filtered.findIndex((s) => s.site_id === customSite.site_id);
    if (idx !== -1) {
      get().setActiveSiteIndex(idx);
    }
  },

  // Delete Custom Site
  deleteCustomSite: async (siteId) => {
    set((state) => {
      const updated = state.allSites.filter((s) => s.site_id !== siteId);
      return { allSites: updated, activeSiteIndex: 0 };
    });
    get().applyFilters();
    const filtered = get().filteredSites;
    if (filtered.length > 0) {
      get().setActiveSiteIndex(0);
    }

    try {
      await fetch('/api/delete-custom-site', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ site_id: siteId }),
      });
    } catch (err) {
      console.error('Failed to delete custom site:', err);
    }
  },

  // Filter Actions
  applyFilters: () => {
    const { allSites, filteredSites, activeSiteIndex, filters } = get();
    const currentSite = filteredSites[activeSiteIndex];

    const filtered = allSites.filter((site) => {
      if (site.is_custom) return true;
      if (filters.city !== 'ALL' && site.city_code !== filters.city) return false;
      if (site.site_area_m2 < filters.minArea || site.site_area_m2 > filters.maxArea) return false;
      const avgH = site.avg_height_m || 0;
      if (avgH < filters.minHeight || avgH > filters.maxHeight) return false;
      return true;
    });

    let newIndex = 0;
    if (filters.activeTier === 'ANY' && currentSite) {
      const idxInFiltered = filtered.findIndex((s) => s.site_id === currentSite.site_id);
      if (idxInFiltered !== -1) newIndex = idxInFiltered;
    }

    set({ filteredSites: filtered, activeSiteIndex: newIndex });

    if (filtered.length > 0) {
      const activeSite = filtered[newIndex];
      get().syncSiteWithOptimizer(activeSite);
    }
  },

  setFilter: (key, value) => {
    set((state) => {
      const updated = { ...state.filters, [key]: value };
      if (key === 'minArea' || key === 'maxArea') {
        let matchedTier = null;
        for (const [tierKey, [tMin, tMax]] of Object.entries(TIER_RANGES)) {
          if (updated.minArea === tMin && updated.maxArea === tMax) {
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

  resetFilters: () => {
    set({ filters: { ...DEFAULT_FILTERS } });
    get().applyFilters();
  },

  navigateCarousel: (delta) => {
    const { filteredSites, activeSiteIndex } = get();
    if (filteredSites.length === 0) return;
    const nextIndex = (activeSiteIndex + delta + filteredSites.length) % filteredSites.length;
    get().setActiveSiteIndex(nextIndex);
  },

  setActiveSiteIndex: (index) => {
    const { filteredSites } = get();
    if (index >= 0 && index < filteredSites.length) {
      set({ activeSiteIndex: index });
      const site = filteredSites[index];
      get().syncSiteWithOptimizer(site);
    }
  },

  pickRandomSite: () => {
    const { filteredSites, activeSiteIndex } = get();
    if (filteredSites.length <= 1) return;
    let randomIndex = Math.floor(Math.random() * (filteredSites.length - 1));
    if (randomIndex >= activeSiteIndex) randomIndex += 1;
    get().setActiveSiteIndex(randomIndex);
  },

  syncSiteWithOptimizer: (site) => {
    if (!site) return;
    get().sendCommand({
      cmd: 'setSite',
      siteId: site.site_id,
      city: site.city_code,
      tier: site.area_tier,
      siteData: site,
    });
  },

  // WebSocket Commands
  sendCommand: (payload) => {
    const { socket, connected } = get();
    if (socket && connected && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(payload));
      return true;
    }
    return false;
  },

  updateSettings: (patch) => {
    set((state) => ({ settings: { ...state.settings, ...patch } }));
    get().sendCommand({ cmd: 'updateSettings', settings: get().settings });
  },

  toggleTraining: () => {
    const { trainingWanted, mode, sendCommand, generationId, episode, step } = get();
    const nextWanted = !trainingWanted;
    set({
      trainingWanted: nextWanted,
      phase: nextWanted ? 'running' : 'paused',
      statusMessage: nextWanted
        ? (mode === 'inference' ? 'Generating building plan...' : 'Training policy active')
        : 'Paused by user',
    });

    if (nextWanted) {
      sendCommand({ cmd: 'step', generationId, episode, step });
    }
  },

  requestNewSite: () => {
    get().navigateCarousel(1);
  },

  resetPolicy: () => {
    get().sendCommand({ cmd: 'resetPolicy' });
    set({ resetConfirmOpen: false });
  },

  saveCheckpoint: () => {
    get().sendCommand({ cmd: 'saveCheckpoint' });
  },

  loadCheckpoint: (fileData) => {
    get().sendCommand({ cmd: 'loadCheckpoint', fileData });
  },

  toggleMerging: () => {
    set((s) => ({ disableMerging: !s.disableMerging }));
  },

  // WebSocket Connection Lifecycle
  initWebSocket: () => {
    get().loadDatasets();
    const wsUrl = `ws://${window.location.host || 'localhost:8000'}/ws`;
    let socket;
    try {
      socket = new WebSocket(wsUrl);
    } catch (e) {
      console.error('Failed to create WebSocket:', e);
      set({ connectionState: 'error' });
      return;
    }

    set({ socket, connectionState: 'connecting' });

    socket.onopen = () => {
      set({ connected: true, connectionState: 'connected', statusMessage: 'Connected to optimizer' });
      get().updateSettings(get().settings);
    };

    socket.onclose = () => {
      set({ connected: false, connectionState: 'disconnected', statusMessage: 'Reconnecting to optimizer...' });
      setTimeout(() => get().initWebSocket(), 2000);
    };

    socket.onerror = () => {
      set({ connectionState: 'error' });
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        get().handleServerEvent(data);
      } catch (err) {
        console.error('Error handling WebSocket message:', err);
      }
    };
  },

  handleServerEvent: (data) => {
    const { type } = data;
    if (type === 'site') {
      const bList = data.boundaries || [];
      const totalArea = bList.reduce((acc, b) => acc + (b.siteArea || 0), 0);
      set({
        hasSite: true,
        generationId: data.generationId,
        episode: data.episode ?? 0,
        step: 0,
        boundaries: bList,
        totalSiteArea: totalArea,
        contextData: data.contextData || null,
        individualPlacementsList: [],
        currentMergedPlacements: [],
        dictionary: data.dictionary || [],
        device: data.device ? data.device.toUpperCase() : 'CPU',
        metrics: data.metrics || get().metrics,
        scoreHistory: data.scoreHistory || [],
        bestScore: data.bestScore ?? get().bestScore,
        statusMessage: `Site ready · ${bList.length} floors`,
      });

      if (get().trainingWanted) {
        get().sendCommand({ cmd: 'step', generationId: data.generationId, episode: data.episode ?? 0, step: 0 });
      }
    } else if (type === 'placements') {
      set((state) => ({
        step: data.step ?? state.step + 1,
        individualPlacementsList: [...state.individualPlacementsList, ...(data.placements || [])],
        currentMergedPlacements: data.mergedPlacements || state.currentMergedPlacements,
        dictionary: data.dictionary || state.dictionary,
        mergedDictionary: data.mergedDictionary || state.mergedDictionary,
        metrics: data.metrics || state.metrics,
        diagnostics: data.diagnostics || state.diagnostics,
        statusMessage: `Episode ${data.episode} · step ${data.step}`,
      }));

      if (get().trainingWanted) {
        setTimeout(() => {
          get().sendCommand({
            cmd: 'step',
            generationId: data.generationId,
            episode: data.episode,
            step: data.step,
          });
        }, 30);
      }
    } else if (type === 'episodeDone') {
      const nextEp = data.nextEpisode ?? get().episode + 1;
      set({
        phase: 'complete',
        episode: data.completedEpisode,
        metrics: data.metrics || get().metrics,
        scoreHistory: data.scoreHistory || get().scoreHistory,
        bestScore: data.bestScore ?? get().bestScore,
        statusMessage: `Episode ${data.completedEpisode} complete`,
      });

      if (get().mode === 'inference' && !get().autoGenerate) {
        set({ trainingWanted: false, phase: 'paused' });
      } else if (get().trainingWanted) {
        set({
          episode: nextEp,
          step: 0,
          individualPlacementsList: [],
          currentMergedPlacements: [],
          phase: 'running',
        });
        setTimeout(() => {
          get().sendCommand({ cmd: 'step', generationId: get().generationId, episode: nextEp, step: 0 });
        }, 100);
      }
    }
  },
}));
