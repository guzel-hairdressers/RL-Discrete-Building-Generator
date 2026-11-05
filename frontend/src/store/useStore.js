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
  learningRate: 0.001,
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
  generatorEngine: 'graph_voronoi',
  graphController: 'neural',
  graphProposalStrategy: 'legacy',
  graphMaxTypes: 15,
  graphPolicyArchitecture: 'message_passing',
  graphSearchMode: 'balanced',
  graphSpatialEnabled: true,
  graphWindowFrontage: 2, graphWindowReferenceArea: 15, graphWindowSeparation: 25, graphWindowCone: 60, graphMaxCreviceFraction: .05, graphPlotDirections: true,
  graphFacadeClearance: 4, graphExposureHorizon: 30, graphDaylightDepth: 6,
  graphMinRoomExposure: .35, graphMaxAccessDistance: 30, graphExposureSampleSpacing: 1,
  graphMinResidentialShare: .65, graphMinCoreArea: 12, graphMinCoreWidth: 2, graphCoreCapacity: 500, graphMinSkyShare: .25, graphMinFill: .4,
};

const DEFAULT_FILTERS = {
  city: 'ALL',
  activeTier: 'ANY',
  minArea: 150,
  maxArea: 10000,
  minHeight: 10,
  maxHeight: 300,
};

let activeStepTimer = null;
function clearActiveStepTimer() {
  if (activeStepTimer != null) {
    clearTimeout(activeStepTimer);
    activeStepTimer = null;
  }
}


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

  // Active client time excludes pauses, previews and disconnected idle time.
  episodeActiveMs: 0,
  episodeClockStartedAt: null,
  episodeClockInitialized: false,
  startEpisodeClock: () => set({ episodeActiveMs: 0, episodeClockStartedAt: performance.now(), episodeClockInitialized: true }),
  resumeEpisodeClock: () => {
    if (!get().episodeClockInitialized) return get().startEpisodeClock();
    if (get().episodeClockStartedAt == null) set({ episodeClockStartedAt: performance.now() });
  },
  elapsedEpisodeMs: () => {
    const s=get();
    return s.episodeClockInitialized ? Math.round(s.episodeActiveMs + (s.episodeClockStartedAt == null ? 0 : performance.now()-s.episodeClockStartedAt)) : null;
  },
  pauseEpisodeClock: () => {
    const elapsed=get().elapsedEpisodeMs();
    if (elapsed != null) set({ episodeActiveMs: elapsed, episodeClockStartedAt: null,
      diagnostics: { ...get().diagnostics, clientWallTimeMs: elapsed } });
  },
  resetEpisodeClock: () => set({ episodeActiveMs: 0, episodeClockStartedAt: null, episodeClockInitialized: false }),

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
  activeTrendMetric: 'fill', // 'reward' | 'fill' | 'rentable' | 'modules' | 'epTime'
  setActiveTrendMetric: (metric) => set({ activeTrendMetric: metric }),
  metrics: {},
  diagnostics: {},
  validation: null,
  predictionErrors: null,
  episodeRecords: [],
  nextEpisode: null,
  pendingSite: false,
  awaitingMode: false,
  stepInFlight: false,
  evaluationInFlight: false,
  selectedFloor: 'all',
  selectedModuleId: null,
  selectedOccurrenceId: null,
  showGraph: true,
  showAccess: false,
  show3D: false,
  setSelectedFloor: (selectedFloor) => set({ selectedFloor }),
  setSelectedModuleId: (id) => set({ selectedModuleId: get().selectedModuleId === id ? null : id, selectedOccurrenceId: null }),
  setSelectedOccurrenceId: (selectedOccurrenceId) => set({ selectedOccurrenceId }),
  setShowGraph: (showGraph) => set({ showGraph }),
  setShowAccess: (showAccess) => set({ showAccess }),
  setShow3D: (show3D) => set({ show3D }),

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
  graphState: null,
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
  activeBottomDrawer: (typeof window !== 'undefined' && window.location && window.location.search && window.location.search.includes('diagnostics')) ? 'diagnostics' : null,
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

    if (get().hasSite && get().settings.boundaryType === 'real' && filtered.length > 0) {
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
        graphState: null,
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
    get().invalidateSite({
      cmd: 'setSite',
      siteId: site.site_id,
      city: site.city_code,
      tier: site.area_tier,
      siteData: site,
    });
  },

  // Command sequencing is independent of animation frames and browser timers.
  sendCommand: (payload) => {
    const { socket, connected } = get();
    if (!socket || !connected || socket.readyState !== WebSocket.OPEN) return false;
    socket.send(JSON.stringify(payload));
    return true;
  },

  invalidateSite: (payload) => {
    clearActiveStepTimer();
    if (get().pendingSite) return false;
    if (!get().sendCommand(payload)) return false;
    get().resetEpisodeClock();
    set({ pendingSite: true, trainingWanted: false, awaitingMode: false,
      phase: 'paused', statusMessage: 'Preparing site…' });
    return true;
  },
  updateSettings: (patch) => get().invalidateSite({ cmd: 'updateSettings', settings: patch }),
  dispatchStep: () => {
    const s = get();
    if (!s.trainingWanted || s.pendingSite || s.awaitingMode || s.stepInFlight || s.evaluationInFlight) return;
    if (s.phase === 'complete') {
      set({ episode: s.nextEpisode ?? s.episode, nextEpisode: null, step: 0, phase: 'running',
        individualPlacementsList: [], currentMergedPlacements: [], completed3DPlacements: [],
        graphState: null, validation: null, predictionErrors: null });
      get().startEpisodeClock();
    }
    const current = get();
    if (get().sendCommand({ cmd: 'step', generationId: current.generationId, episode: current.episode })) {
      set({ stepInFlight: true });
    }
  },
  startExecution: (mode) => {
    if (!get().connected || !get().hasSite || get().pendingSite || get().stepInFlight || get().evaluationInFlight) return;
    if (get().phase === 'complete' || !get().episodeClockInitialized) get().startEpisodeClock();
    else get().resumeEpisodeClock();
    set({ mode, trainingWanted: true, awaitingMode: true,
      statusMessage: mode === 'training' ? 'Starting training…' : 'Generating one layout…' });
    get().sendCommand({ cmd: 'setMode', mode });
  },
  startTraining: () => get().startExecution('training'),
  startInference: () => get().startExecution('inference'),
  requestEvaluation: () => {
    const s = get();
    if (s.pendingSite || s.stepInFlight || s.evaluationInFlight || !s.hasSite) return;
    if (s.sendCommand({ cmd: 'evaluate', generationId: s.generationId, episode: s.nextEpisode ?? s.episode })) {
      set({ evaluationInFlight: true, statusMessage: 'Checking geometry…' });
    }
  },
  pauseExecution: () => {
    get().pauseEpisodeClock();
    clearActiveStepTimer();
    set({ trainingWanted: false, awaitingMode: false, phase: 'paused', statusMessage: 'Paused' });
    if (!get().stepInFlight) get().requestEvaluation();
  },
  toggleTraining: () => get().trainingWanted ? get().pauseExecution() : get().startExecution(get().mode),
  requestNewSite: () => {
    if (get().settings.boundaryType === 'real' && get().filteredSites.length > 1) get().navigateCarousel(1);
    else get().invalidateSite({ cmd: 'newSite' });
  },
  resetPolicy: () => {
    get().invalidateSite({ cmd: 'resetPolicy' });
    set({ resetConfirmOpen: false });
  },
  saveCheckpoint: () => get().sendCommand({ cmd: 'saveCheckpoint' }),
  loadCheckpoint: (fileData) => get().invalidateSite({ cmd: 'loadCheckpoint', fileData }),
  toggleMerging: () => set((s) => ({ disableMerging: !s.disableMerging })),

  initWebSocket: () => {
    // StrictMode mounts effects twice. Keep one connection and one isolated trainer.
    if (get().socket && get().socket.readyState < 2) return;
    get().loadDatasets();
    const socket = new WebSocket(`${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`);
    set({ socket, connectionState: 'connecting' });
    socket.onopen = () => {
      set({ connected: true, connectionState: 'connected', pendingSite: false });
      get().updateSettings(get().settings);
    };
    socket.onclose = () => {
      if (get().socket !== socket) return;
      get().pauseEpisodeClock();
      set({ connected: false, connectionState: 'disconnected', trainingWanted: false,
        pendingSite: false, stepInFlight: false, evaluationInFlight: false, awaitingMode: false,
        phase: 'paused', statusMessage: 'Connection lost · reconnecting' });
      setTimeout(() => get().initWebSocket(), 2000);
    };
    socket.onerror = () => set({ connectionState: 'error' });
    socket.onmessage = (event) => {
      try { get().handleServerEvent(JSON.parse(event.data)); }
      catch (error) { console.error('Invalid optimizer event', error); }
    };
  },

  handleServerEvent: (data) => {
    const { type } = data;
    if (type === 'ack') {
      if (data.command === 'setMode' && get().awaitingMode) {
        set({ awaitingMode: false, mode: data.mode ?? get().mode,
          generationId: data.generationId ?? get().generationId,
          episode: data.episode ?? get().episode, nextEpisode: null, phase: 'running' });
        get().dispatchStep();
      } else if (data.command === 'saveCheckpoint') set({ statusMessage: data.message });
      return;
    }
    if (type === 'error') {
      get().pauseEpisodeClock();
      clearActiveStepTimer();
      set({ trainingWanted: false, pendingSite: false, awaitingMode: false,
        stepInFlight: false, evaluationInFlight: false, phase: 'paused',
        statusMessage: data.message || data.error || 'Optimizer rejected the command' });
      return;
    }
    if (type === 'site') {
      if (get().hasSite && data.generationId < get().generationId) return;
      get().resetEpisodeClock();
      const bList = data.boundaries || [];
      const contextSiteId = data.contextData?.site_id;
      const idx = get().filteredSites.findIndex((s) => s.site_id === contextSiteId);
      set({ hasSite: true, pendingSite: false, stepInFlight: false, evaluationInFlight: false,
        generationId: data.generationId, episode: data.episode ?? 0, nextEpisode: null, step: 0,
        settings: data.settings || get().settings, boundaries: bList,
        totalSiteArea: bList.reduce((sum, b) => sum + (b.siteArea ?? b.exactArea ?? 0), 0),
        contextData: data.contextData || null, activeSiteIndex: idx >= 0 ? idx : get().activeSiteIndex,
        individualPlacementsList: [], currentMergedPlacements: [], completed3DPlacements: [],
        graphState: null, validation: null, predictionErrors: null, selectedOccurrenceId: null,
        selectedFloor: get().selectedFloor !== 'all' && Number(get().selectedFloor) >= bList.length ? 'all' : get().selectedFloor,
        dictionary: data.dictionary || [], mergedDictionary: [], metrics: data.metrics || {}, diagnostics: {},
        device: data.device?.toUpperCase() || get().device,
        statusMessage: `Site ready · ${bList.length} floors`,
      });
      if (get().trainingWanted) { get().startEpisodeClock(); get().dispatchStep(); }
      return;
    }
    // Drop replies from a replaced generation, and queued replies while replacing a site.
    if (get().pendingSite || (data.generationId != null && data.generationId !== get().generationId)) return;
    if (!['placements', 'episodeDone', 'sync'].includes(type)) return;
    const isEval = Boolean(data.isEvaluation);
    const completed = type === 'episodeDone';
    const expectedEpisode = get().nextEpisode ?? get().episode;
    // Evaluation of the last completed layout is tagged with its inspected episode.
    if (!completed && !isEval && data.episode != null && data.episode !== expectedEpisode) return;
    if (completed && data.completedEpisode != null && data.completedEpisode !== get().episode) return;
    if (isEval && data.episode != null && ![get().episode, expectedEpisode].includes(data.episode)) return;
    if (isEval && get().trainingWanted) return;
    const wasRunning = get().trainingWanted;
    const graphOnly = data.graphState && !data.graphState.realized;
    const placements = data.placements || [];
    let nextList = placements;
    if (!graphOnly && !isEval && !completed && type !== 'sync') {
      const map = new Map(get().individualPlacementsList.map((p) => [p.id, p]));
      placements.forEach((p) => map.set(p.id, p)); nextList = [...map.values()];
    }
    if (completed && !data.placements && !graphOnly) nextList = get().individualPlacementsList;
    const merged = data.graphState ? nextList : (data.mergedPlacements?.length ? data.mergedPlacements : nextList);
    const effectiveMetrics = { ...(data.metrics || get().metrics) };
    const validation = data.validation ?? (graphOnly ? null : get().validation);
    if (completed) get().pauseEpisodeClock();
    const wall = get().elapsedEpisodeMs();
    const diagnostics = { ...get().diagnostics, ...data.diagnostics, ...effectiveMetrics.runtimeDiagnostics, clientWallTimeMs: wall };
    if (completed) {
      diagnostics.episodeTimeMs = effectiveMetrics.episodeExecutionTimeMs ?? data.diagnostics?.episodeTimeMs ?? null;
      diagnostics.postStepEvaluationMs = effectiveMetrics.postStepEvaluationMs ?? data.diagnostics?.postStepEvaluationMs ?? null;
      diagnostics.clientWallTimeMs = wall;
    }
    set({ stepInFlight: isEval ? get().stepInFlight : false,
      evaluationInFlight: isEval ? false : get().evaluationInFlight,
      step: data.step ?? get().step,
      episode: completed ? (data.completedEpisode ?? data.episode ?? get().episode) : (isEval && get().nextEpisode != null ? get().episode : (data.episode ?? get().episode)),
      nextEpisode: completed ? data.nextEpisode : get().nextEpisode,
      graphState: data.graphState ?? (type === 'sync' ? null : get().graphState),
      individualPlacementsList: nextList, currentMergedPlacements: merged,
      completed3DPlacements: completed || isEval || type === 'sync' ? merged : (graphOnly ? [] : get().completed3DPlacements),
      dictionary: data.dictionary ?? get().dictionary, mergedDictionary: data.mergedDictionary ?? get().mergedDictionary,
      metrics: effectiveMetrics, diagnostics, validation,
      predictionErrors: data.predictionErrors ?? get().predictionErrors,
      phase: completed ? 'complete' : get().phase,
      statusMessage: isEval ? 'Geometry preview ready' : completed ? `Episode ${data.completedEpisode ?? data.episode} complete` : `Episode ${data.episode} · batch ${data.step}`,
    });
    if (completed) {
      const record = { episode: get().episode, mode: get().mode, realized: Boolean(data.graphState?.realized),
        fill: effectiveMetrics.fillRatio ?? null, reuse: effectiveMetrics.reuseAudit?.independentRepeatFraction ?? null,
        exposure: effectiveMetrics.daylightAccessProxy ?? null,
        windows: effectiveMetrics.windowFrontageRatio ?? null,
        spatialRequirementsMet: effectiveMetrics.spatialRequirementsMet ?? null,
        valid: validation?.valid ?? null, graphValid: validation?.graphValid ?? effectiveMetrics.graphValid ?? null,
        serverMs: diagnostics.episodeTimeMs, wallMs: wall, score: effectiveMetrics.score ?? null };
      set((s) => ({ episodeRecords: [...s.episodeRecords, record],
        fillHistory: [...s.fillHistory, record.fill == null ? null : record.fill * 100],
        rentableHistory: [...s.rentableHistory, effectiveMetrics.rentableRatio == null ? null : effectiveMetrics.rentableRatio * 100],
        modulesHistory: [...s.modulesHistory, effectiveMetrics.moduleCount ?? effectiveMetrics.graphNodes ?? null],
        epTimeHistory: [...s.epTimeHistory, record.serverMs],
        rewardHistory: data.scoreHistory ?? s.rewardHistory, bestReward: data.bestScore ?? s.bestReward }));
      if (get().mode === 'inference') { set({ trainingWanted: false }); return; }
      if (!wasRunning) { get().requestEvaluation(); return; }
      const count = get().episodesOnCurrentSite + 1;
      const limit = get().settings.autoChangeEpisodes ?? 1;
      set({ episodesOnCurrentSite: count });
      if (limit <= 20 && count >= limit) {
        // Keep run intent across the authoritative site transaction.
        get().requestNewSite();
        set({ trainingWanted: true, episodesOnCurrentSite: 0 });
      } else get().dispatchStep();
    } else if (!isEval && type !== 'sync') {
      if (wasRunning) get().dispatchStep();
      else get().requestEvaluation();
    }
  },
}));
