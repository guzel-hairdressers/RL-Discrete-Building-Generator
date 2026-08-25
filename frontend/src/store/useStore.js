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
  autoChangeEpisodes: 1, // 1 to 20, or 21 (displayed as '∞' / 'Never')
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
  episodesOnCurrentSite: 0,
  bestReward: -40.0,
  rewardHistory: [],
  fillHistory: [],
  rentableHistory: [],
  modulesHistory: [],
  epTimeHistory: [],
  activeTrendMetric: 'reward', // 'reward' | 'fill' | 'rentable' | 'modules' | 'epTime'
  setActiveTrendMetric: (metric) => set({ activeTrendMetric: metric }),
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
  completed3DPlacements: [], // Only updated when an episode finishes
  dictionary: [],
  mergedDictionary: [],
  contextData: null,

  // 3D & 2D View Controls
  viewMode: 'axonometric',
  visualsEnabled: true, // headless/visuals toggle — default visuals ON; OFF stops the browser render loop + display formatting (monitoring continues)
  maximizedPane: null,
  hoveredModuleId: null,

  // Settings & Expandable Bottom Panels
  settings: { ...DEFAULT_SETTINGS },
  activeBottomDrawer: null, // null | 'settings' | 'diagnostics'
  resetConfirmOpen: false,

  // Setters & Panel Toggles
  setCustomModalOpen: (open) => set({ customModalOpen: open }),
  setMode: (newMode) => {
    set({ mode: newMode });
    get().sendCommand({ cmd: 'setMode', mode: newMode });
  },
  setActiveBottomDrawer: (drawer) => {
    set((s) => ({ activeBottomDrawer: s.activeBottomDrawer === drawer ? null : drawer }));
  },
  setResetConfirmOpen: (open) => set({ resetConfirmOpen: open }),
  setViewMode: (mode) => set({ viewMode: mode }),
  setVisualsEnabled: (enabled) => {
    const flag = !!enabled;
    set({ visualsEnabled: flag });
    get().sendCommand({ cmd: 'setVisuals', enabled: flag });
    if (flag) {
      // Re-enabling without a reload / weight reload: while visuals were OFF the
      // server stopped shipping geometry, so pull a full fresh snapshot (getState
      // still builds the complete payload) so the 3D+2D scenes repaint from the
      // live optimizer state rather than a stale client cache.
      get().sendCommand({ cmd: 'getState' });
    }
  },
  setMaximizedPane: (pane) => set((s) => ({ maximizedPane: s.maximizedPane === pane ? null : pane })),
  setHoveredModuleId: (id) => set({ hoveredModuleId: id }),

  // Set Boundary Type (Family)
  setBoundaryType: (type) => {
    get().updateSettings({ boundaryType: type });
    if (type !== 'real') {
      get().requestNewSite();
    }
  },

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
      set({
        activeSiteIndex: index,
        individualPlacementsList: [],
        currentMergedPlacements: [],
        completed3DPlacements: [],
      });
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

  // Execution Control: Split Training / Inference & Pause
  startTraining: () => {
    set((state) => ({
      mode: 'training',
      trainingWanted: true,
      phase: 'running',
      individualPlacementsList: (state.step === 0 || state.phase === 'complete') ? [] : state.individualPlacementsList,
      currentMergedPlacements: [],
      completed3DPlacements: [],
      statusMessage: 'Training policy active',
    }));
    get().sendCommand({ cmd: 'setMode', mode: 'training' });
    get().sendCommand({
      cmd: 'step',
      generationId: get().generationId,
      episode: get().episode,
      step: get().step,
    });
  },

  startInference: () => {
    set({
      mode: 'inference',
      trainingWanted: true,
      phase: 'running',
      completed3DPlacements: [],
      currentMergedPlacements: [],
      statusMessage: 'Generating building plan (Inference)...',
    });
    get().sendCommand({ cmd: 'setMode', mode: 'inference' });
    get().sendCommand({
      cmd: 'step',
      generationId: get().generationId,
      episode: get().episode,
      step: get().step,
    });
  },

  pauseExecution: () => {
    set({
      trainingWanted: false,
      phase: 'paused',
      statusMessage: 'Paused by user',
    });
    get().sendCommand({
      cmd: 'evaluate',
      generationId: get().generationId,
      episode: get().episode,
    });
  },

  toggleTraining: () => {
    const { trainingWanted, startTraining, pauseExecution } = get();
    if (trainingWanted) {
      pauseExecution();
    } else {
      startTraining();
    }
  },

  requestNewSite: () => {
    const { settings, sendCommand } = get();
    set({
      individualPlacementsList: [],
      currentMergedPlacements: [],
      completed3DPlacements: [],
    });
    if (settings.boundaryType === 'real') {
      get().navigateCarousel(1);
    } else {
      sendCommand({ cmd: 'newSite' });
    }
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
        completed3DPlacements: [],
        dictionary: data.dictionary || [],
        device: data.device ? data.device.toUpperCase() : 'CPU',
        metrics: data.metrics || get().metrics,
        rewardHistory: data.scoreHistory || [],
        bestReward: data.bestScore ?? get().bestReward,
        statusMessage: `Site ready · ${bList.length} floors`,
      });

      if (get().trainingWanted) {
        get().sendCommand({ cmd: 'step', generationId: data.generationId, episode: data.episode ?? 0, step: 0 });
      }
    } else if (type === 'placements') {
      const incomingMerged = (Array.isArray(data.mergedPlacements) && data.mergedPlacements.length > 0)
        ? data.mergedPlacements
        : null;

      const isEval = !!data.isEvaluation;

      set((state) => {
        let nextList;
        if (isEval || (data.step != null && data.step <= 1) || (data.episode != null && data.episode !== state.episode)) {
          nextList = data.placements || [];
        } else {
          const idMap = new Map();
          state.individualPlacementsList.forEach((p) => { if (p && p.id) idMap.set(p.id, p); });
          (data.placements || []).forEach((p) => { if (p && p.id) idMap.set(p.id, p); });
          nextList = Array.from(idMap.values());
        }

        return {
          step: data.step ?? state.step + 1,
          episode: data.episode ?? state.episode,
          individualPlacementsList: nextList,
          currentMergedPlacements: incomingMerged || ((data.step != null && data.step <= 1) ? [] : state.currentMergedPlacements),
          dictionary: data.dictionary || state.dictionary,
          mergedDictionary: data.mergedDictionary || state.mergedDictionary,
          metrics: data.metrics || state.metrics,
          diagnostics: data.diagnostics || state.diagnostics,
          statusMessage: `Episode ${data.episode} · step ${data.step}`,
        };
      });

      if (get().trainingWanted) {
        setTimeout(() => {
          get().sendCommand({
            cmd: 'step',
            generationId: Number(data.generationId ?? get().generationId),
            episode: Number(data.episode ?? get().episode),
            step: Number(data.step ?? get().step),
          });
        }, 0);
      }
    } else if (type === 'error') {
      console.warn('Server error received:', data);
      if (get().trainingWanted) {
        setTimeout(() => {
          get().sendCommand({
            cmd: 'step',
            generationId: Number(data.generationId ?? get().generationId),
            episode: Number(data.episode ?? get().episode),
            step: Number(get().step),
          });
        }, 50);
      }
    } else if (type === 'episodeDone') {
      const nextEp = data.nextEpisode ?? get().episode + 1;

      // Update completed3DPlacements so the 3D and 2D scenes capture the finalized building at episode completion!
      const finalized = (data.mergedPlacements && data.mergedPlacements.length > 0)
        ? data.mergedPlacements
        : (get().currentMergedPlacements && get().currentMergedPlacements.length > 0
            ? get().currentMergedPlacements
            : get().individualPlacementsList);

      const effectiveMetrics = data.metrics || get().metrics;
      const currentFillPct = Math.round(((effectiveMetrics.fillRatio) || 0) * 1000) / 10;
      const currentRentablePct = Math.round(((effectiveMetrics.rentableRatio) || 0) * 1000) / 10;
      const currentModulesCount = effectiveMetrics.placedCount ?? get().step ?? 0;
      const currentEpTime = Math.round(data.diagnostics?.episodeTimeMs || (currentModulesCount * (data.diagnostics?.stepTimeMs || 4.2)) || 142);

      set((state) => ({
        phase: 'complete',
        episode: data.completedEpisode,
        completed3DPlacements: finalized,
        currentMergedPlacements: finalized,
        metrics: effectiveMetrics,
        rewardHistory: data.scoreHistory || state.rewardHistory,
        fillHistory: [...state.fillHistory, currentFillPct],
        rentableHistory: [...state.rentableHistory, currentRentablePct],
        modulesHistory: [...state.modulesHistory, currentModulesCount],
        epTimeHistory: [...state.epTimeHistory, currentEpTime],
        bestReward: data.bestScore ?? state.bestReward,
        statusMessage: `Episode ${data.completedEpisode} complete`,
      }));

      const autoChangeLimit = get().settings.autoChangeEpisodes ?? 1;
      const currentSiteCount = (get().episodesOnCurrentSite || 0) + 1;

      if (get().mode === 'inference' && !get().autoGenerate) {
        set({ trainingWanted: false, phase: 'paused', episodesOnCurrentSite: currentSiteCount });
      } else if (get().trainingWanted) {
        const shouldChangeSite = (autoChangeLimit <= 20) && (currentSiteCount >= autoChangeLimit);

        if (shouldChangeSite) {
          setTimeout(() => {
            if (get().trainingWanted) {
              set({
                episodesOnCurrentSite: 0,
                episode: nextEp,
                step: 0,
                individualPlacementsList: [],
                currentMergedPlacements: [],
                completed3DPlacements: [],
                phase: 'running',
              });
              get().requestNewSite();
            }
          }, 400);
        } else {
          setTimeout(() => {
            if (get().trainingWanted) {
              set({
                episodesOnCurrentSite: currentSiteCount,
                episode: nextEp,
                step: 0,
                individualPlacementsList: [],
                currentMergedPlacements: [],
                completed3DPlacements: [],
                phase: 'running',
              });
              get().sendCommand({
                cmd: 'step',
                generationId: Number(get().generationId),
                episode: Number(nextEp),
                step: 0,
              });
            }
          }, 100);
        }
      }
    } else if (type === 'sync') {
      // Response to the `getState` command sent when visuals are re-enabled. This
      // is a non-mutating full snapshot (placements + boundaries + dictionary +
      // metrics) rebuilt by the server even when visuals were off, so the client
      // can repaint the 3D/2D scenes from live state — no page reload, no weight
      // reload. Setting the placement/merged lists here triggers ThreeViewer's
      // extrusion-sync effect, which re-posts optimizer_placements to the iframe.
      set({
        boundaries: data.boundaries || [],
        dictionary: data.dictionary || [],
        mergedDictionary: data.mergedDictionary || [],
        individualPlacementsList: data.placements || [],
        currentMergedPlacements: data.mergedPlacements || [],
        completed3DPlacements: (Array.isArray(data.mergedPlacements) && data.mergedPlacements.length > 0)
          ? data.mergedPlacements
          : (data.placements || []),
        metrics: data.metrics || get().metrics,
        diagnostics: data.diagnostics || get().diagnostics,
        rewardHistory: data.scoreHistory || get().rewardHistory,
        bestReward: data.bestScore ?? get().bestReward,
        totalSiteArea: (data.boundaries || []).reduce((acc, b) => acc + (b.siteArea || 0), 0),
        contextData: data.contextData ?? get().contextData,
        statusMessage: 'Visuals re-enabled · scene refreshed',
      });
    }
  },
}));
