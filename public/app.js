window.onerror = function(message, source, lineno, colno, error) {
  const errText = `JS Error: ${message} at ${source}:${lineno}:${colno}`;
  console.error(errText);
  const emptyDiv = document.getElementById('canvasEmpty');
  if (emptyDiv) {
    emptyDiv.style.display = 'flex';
    emptyDiv.style.color = '#d16a50';
    emptyDiv.style.backgroundColor = '#faf9f5';
    emptyDiv.innerText = errText;
  }
};

(() => {
  'use strict';

  const CATEGORY_COLORS = Object.freeze({
    core: '#dc745d',
    corridor: '#e1ba57',
    room: '#a9c5ae',
    special: '#6e9c89'
  });

  const INTEGER_SETTINGS = new Set([
    'parallelEnvironments',
    'maxModules',
    'dictCap',
    'travelLimit',
    'maxRoomHops'
  ]);

  const SETTING_KEYS = Object.freeze([
    'boundaryType',
    'siteAreaTier',
    'atriumPolicy',
    'singleFloor',
    'publicMode',
    'parallelEnvironments',
    'maxModules',
    'learningRate',
    'minEdge',
    'maxEdge',
    'dictCap',
    'angleStep',
    'coreSpacing',
    'travelLimit',
    'maxRoomHops',
    'allowStop'
  ]);

  const MAX_RETAINED_SCORE_HISTORY = 10000;
  const DEBUG_SCORE_POINT_LIMIT = 120;
  const DEBUG_METRIC_KEYS = Object.freeze([
    'score', 'fillRatio', 'rentableRatio', 'daylightRatio', 'reuseRatio',
    'constructibilityScore', 'envelopeEfficiency', 'rawScore',
    'areaVariancePenalty', 'internalExposedPenalty', 'partialConnectionPenalty',
    'deepInteriorPenalty', 'facadeChasmPenalty', 'deepRoomRatio', 'facadeChasmRatio',
    'topologyPenalty', 'bpeBonus', 'unmergedTrianglePenalty',
    'relativeTimeReward', 'dictBreachPenalty', 'candidateEvaluations',
    'generationTimeSeconds', 'sizeNormalizedGenerationTime', 'policyLoss',
    'actorLoss', 'valueLoss', 'policyEntropy', 'gradientNorm', 'advantage',
    'learningRate', 'learningAlgorithm', 'baseline'
  ]);
  const DEBUG_TIMING_KEYS = Object.freeze([
    'candidateGeneration', 'policyInference', 'shapeSynthesis', 'placement',
    'bpeMerge', 'stepTotal', 'terminalMetrics', 'aggregateTerminal',
    'episodeBpeMerge', 'learning', 'dictSynthesis', 'episodeFormatting',
    'episodeTotal'
  ]);

  const dom = {
    stage: document.getElementById('stage'),
    canvas: document.getElementById('planCanvas'),
    connectionBadge: document.getElementById('connectionBadge'),
    connectionText: document.getElementById('connectionText'),
    deviceBadge: document.getElementById('deviceBadge'),
    scoreValue: document.getElementById('scoreValue'),
    bestScoreValue: document.getElementById('bestScoreValue'),
    fillValue: document.getElementById('fillValue'),
    filledAreaValue: document.getElementById('filledAreaValue'),
    rentableValue: document.getElementById('rentableValue'),
    siteMetricList: document.getElementById('siteMetricList'),
    episodeValue: document.getElementById('episodeValue'),
    environmentValue: document.getElementById('environmentValue'),
    stepValue: document.getElementById('stepValue'),
    moduleCountValue: document.getElementById('moduleCountValue'),
    canvasMessage: document.getElementById('canvasMessage'),
    canvasMessageTitle: document.getElementById('canvasMessageTitle'),
    canvasMessageBody: document.getElementById('canvasMessageBody'),
    toastRegion: document.getElementById('toastRegion'),
    fitViewBtn: document.getElementById('fitViewBtn'),
    panelToggle: document.getElementById('panelToggle'),
    panelClose: document.getElementById('panelClose'),
    panelScrim: document.getElementById('panelScrim'),
    controlsPanel: document.getElementById('controlsPanel'),
    pauseBtn: document.getElementById('pauseBtn'),
    newSiteBtn: document.getElementById('newSiteBtn'),
    resetPolicyBtn: document.getElementById('resetPolicyBtn'),
    saveCheckpointBtn: document.getElementById('saveCheckpointBtn'),
    loadCheckpointBtn: document.getElementById('loadCheckpointBtn'),
    resetConfirmModal: document.getElementById('resetConfirmModal'),
    cancelResetBtn: document.getElementById('cancelResetBtn'),
    confirmResetBtn: document.getElementById('confirmResetBtn'),
    weightFileInput: document.getElementById('weightFileInput'),
    settingsForm: document.getElementById('settingsForm'),
    settingsError: document.getElementById('settingsError'),
    legendSpecial: document.getElementById('legendSpecial'),
    dictionaryList: document.getElementById('dictionaryList'),
    dictionaryCount: document.getElementById('dictionaryCount'),
    historyCanvas: document.getElementById('historyCanvas'),
    trendValue: document.getElementById('trendValue'),
    trendKicker: document.getElementById('trendKicker'),
    trendTitle: document.getElementById('trendTitle'),
    protocolStatus: document.getElementById('protocolStatus'),
    speed: document.getElementById('speed'),
    speedNum: document.getElementById('speedNum'),
    toggleMergingBtn: document.getElementById('toggleMergingBtn'),
    perfTimingsCard: document.getElementById('perfTimingsCard'),
    perfTimingsDetails: document.getElementById('perfTimingsDetails'),
    modeTrainingBtn: document.getElementById('modeTrainingBtn'),
    modeInferenceBtn: document.getElementById('modeInferenceBtn'),
    autoGenerateCheckbox: document.getElementById('autoGenerateCheckbox'),
    inferenceOptions: document.getElementById('inferenceOptions'),
    panelConsoleKicker: document.getElementById('panelConsoleKicker'),
    developerToggle: document.getElementById('developerToggle'),
    developerPanel: document.getElementById('developerPanel'),
    developerClose: document.getElementById('developerClose'),
    debugEpisodeMeta: document.getElementById('debugEpisodeMeta'),
    debugScoreCanvas: document.getElementById('debugScoreCanvas'),
    debugScoreSummary: document.getElementById('debugScoreSummary'),
    debugRewardBreakdown: document.getElementById('debugRewardBreakdown'),
    debugRuntimeMetrics: document.getElementById('debugRuntimeMetrics'),
    debugTrainingMetrics: document.getElementById('debugTrainingMetrics'),
    debugTimingRows: document.getElementById('debugTimingRows')
  };

  const context = dom.canvas.getContext('2d', { alpha: false });

  const state = {
    socket: null,
    socketSerial: 0,
    connected: false,
    connectionState: 'connecting',
    reconnectAttempt: 0,
    reconnectTimer: null,
    manuallyClosed: false,

    mode: 'training',
    autoGenerate: false,
    trainingWanted: false,
    phase: 'connecting',
    hasSite: false,
    awaitingSite: true,
    generationId: null,
    episode: null,
    pendingNextEpisode: null,
    pendingNextDictionary: null,
    step: 0,
    stepInFlight: false,
    stepTimer: null,
    transitionTimer: null,
    siteMetricTimer: null,
    lastSiteMetricUpdatedAt: 0,
    lastStepSentAt: 0,

    settings: null,
    acceptedSettings: null,
    pendingSettings: null,
    settingsDirty: false,
    settingsTimer: null,
    speed: 100,

    device: null,
    boundaries: [],
    boundaryByInstance: new Map(),
    dictionary: [],
    mergedDictionary: [],
    placements: new Map(),
    placementOrder: [],
    graphEdges: new Map(),
    areasByInstance: new Map(),
    totalSiteArea: 0,
    totalFilledArea: 0,
    totalRentableArea: 0,
    placementRevision: 0,
    disableMerging: false,
    autoChangeSites: true,
    showSDFGrid: false,
    hoveredModuleId: null,
    lastHoveredModuleId: null,
    dimmingFactor: 0.0,
    lastFrameTime: null,

    serverMetrics: {},
    scoreHistory: [],
    showFullHistory: false,
    historyHovered: false,
    historyHoverFactor: 0.0,
    historyHoverAnimFrame: null,
    bestScore: 0,
    developerOpen: false,
    developerUpdateFrame: null,
    debugScoreSignature: null,
    nativeGeometryTelemetry: null,
    memoryTelemetry: null,
    debugTelemetry: {},

    wallCache: null,
    wallJobToken: 0,
    wallComputing: false,
    wallSchedule: null,
    wallWorker: null
  };

  const panelMediaQuery = window.matchMedia('(max-width: 1040px)');
  let panelReturnFocus = null;
  let developerReturnFocus = null;

  const view = {
    width: 1,
    height: 1,
    dpr: 1,
    zoom: 12,
    panX: 0,
    panY: 0,
    minZoom: 1.5,
    maxZoom: 80,
    userAdjusted: false,
    renderFrame: null,
    pointers: new Map(),
    gesture: null
  };

  function init() {
    setupControlPairs();
    setupSettingsEvents();
    setupActionEvents();
    setupPanelEvents();
    setupDeveloperEvents();
    setupCanvasEvents();
    setupResizeHandling();

    const validation = readAndValidateSettings();
    if (validation.ok) {
      state.settings = validation.settings;
    }
    state.speed = Number(dom.speed.value) || 100;

    updatePauseButton();
    updateActionAvailability();
    updateMetricsUI();
    updateAccessibleSiteMetrics();
    updateDictionaryUI();
    drawHistory();
    resizeCanvas();
    requestRender();
    connectWebSocket();
  }

  function setupControlPairs() {
    document.querySelectorAll('.range-field').forEach((field) => {
      const range = field.querySelector('input[type="range"]');
      const number = field.querySelector('input[type="number"]');
      if (!range || !number) return;

      const syncFromRange = () => {
        number.value = range.value;
        number.removeAttribute('aria-invalid');
        updateRangeProgress(range);
        handleControlChange(range);
      };

      const syncFromNumber = () => {
        if (number.value === '' || !number.validity.valid) {
          number.setAttribute('aria-invalid', 'true');
          showSettingsError(`Enter a value from ${number.min} to ${number.max}.`);
          return;
        }
        range.value = number.value;
        number.value = range.value;
        number.removeAttribute('aria-invalid');
        updateRangeProgress(range);
        handleControlChange(range);
      };

      range.addEventListener('input', syncFromRange);
      number.addEventListener('input', syncFromNumber);
      number.addEventListener('change', () => {
        if (number.value === '') number.value = range.value;
        syncFromNumber();
      });
      updateRangeProgress(range);
    });
  }

  function setupSettingsEvents() {
    dom.settingsForm.querySelectorAll('select[data-setting], input[type="checkbox"][data-setting]').forEach((control) => {
      control.addEventListener('change', () => handleControlChange(control));
    });
  }

  function handleControlChange(control) {
    if (control.hasAttribute('data-client-only')) {
      state.speed = clamp(Number(control.value) || 1, 1, 100);
      if (state.trainingWanted && state.hasSite && !state.awaitingSite && !state.stepInFlight) {
        scheduleNextStep();
      }
      return;
    }

    const validation = readAndValidateSettings();
    if (!validation.ok) return;

    state.settings = validation.settings;
    state.settingsDirty = true;
    updateMetricsUI();
    updateActionAvailability();
    clearTimeout(state.settingsTimer);
    state.settingsTimer = window.setTimeout(applySettingsAndRefreshSite, 360);
  }

  function readAndValidateSettings() {
    const settings = {};
    const errors = [];

    dom.settingsForm.querySelectorAll('.range-field input[type="number"]').forEach((numberInput) => {
      if (numberInput.value === '' || !numberInput.validity.valid) {
        numberInput.setAttribute('aria-invalid', 'true');
        const fieldLabel = numberInput.closest('.range-field')?.querySelector('label');
        errors.push(`${fieldLabel ? fieldLabel.textContent.trim() : 'A numeric value'} is outside its allowed range.`);
      } else {
        numberInput.removeAttribute('aria-invalid');
      }
    });

    for (const key of SETTING_KEYS) {
      const control = document.getElementById(key);
      if (!control) {
        errors.push(`Missing setting: ${key}`);
        continue;
      }

      control.removeAttribute('aria-invalid');
      if (control.type === 'checkbox') {
        settings[key] = control.checked;
      } else if (control.tagName === 'SELECT') {
        settings[key] = control.value;
      } else {
        const value = Number(control.value);
        if (!Number.isFinite(value) || !control.validity.valid) {
          control.setAttribute('aria-invalid', 'true');
          errors.push(`${labelFor(control)} is outside its allowed range.`);
        } else {
          settings[key] = INTEGER_SETTINGS.has(key) ? Math.round(value) : value;
        }
      }
    }

    if (Number.isFinite(settings.minEdge) && Number.isFinite(settings.maxEdge) && settings.minEdge > settings.maxEdge) {
      document.getElementById('minEdge').setAttribute('aria-invalid', 'true');
      document.getElementById('maxEdge').setAttribute('aria-invalid', 'true');
      errors.push('Minimum edge cannot be greater than maximum edge.');
    }

    if (errors.length) {
      showSettingsError(errors[0]);
      return { ok: false, settings: null };
    }

    hideSettingsError();
    return { ok: true, settings };
  }

  function labelFor(control) {
    const label = dom.settingsForm.querySelector(`label[for="${control.id}"]`);
    return label ? label.textContent.trim() : control.name || control.id;
  }

  function showSettingsError(message) {
    dom.settingsError.textContent = message;
    dom.settingsError.hidden = false;
  }

  function hideSettingsError() {
    dom.settingsError.textContent = '';
    dom.settingsError.hidden = true;
  }

  function copySettings(settings) {
    return settings ? { ...settings } : null;
  }

  function restoreSettingsControls(settings) {
    if (!settings) return;
    for (const key of SETTING_KEYS) {
      const control = document.getElementById(key);
      if (!control || !Object.prototype.hasOwnProperty.call(settings, key)) continue;
      if (control.type === 'checkbox') control.checked = Boolean(settings[key]);
      else control.value = String(settings[key]);
      control.removeAttribute('aria-invalid');

      if (control.type === 'range') {
        const number = document.getElementById(`${key}Num`);
        if (number) {
          number.value = control.value;
          number.removeAttribute('aria-invalid');
        }
        updateRangeProgress(control);
      }
    }
    state.settings = copySettings(settings);
    hideSettingsError();
  }

  function updateRangeProgress(range) {
    const min = Number(range.min) || 0;
    const max = Number(range.max) || 100;
    const value = Number(range.value) || 0;
    const progress = max === min ? 0 : ((value - min) / (max - min)) * 100;
    range.style.setProperty('--range-progress', `${clamp(progress, 0, 100)}%`);
  }

  function setupActionEvents() {
    dom.pauseBtn.addEventListener('click', toggleTraining);
    dom.newSiteBtn.addEventListener('click', requestNewSite);
    dom.resetPolicyBtn.addEventListener('click', resetPolicy);
    dom.saveCheckpointBtn.addEventListener('click', saveCheckpoint);
    dom.loadCheckpointBtn.addEventListener('click', loadCheckpoint);
    dom.weightFileInput.addEventListener('change', handleWeightFileSelect);
    dom.cancelResetBtn.addEventListener('click', hideResetConfirmation);
    dom.confirmResetBtn.addEventListener('click', confirmResetPolicy);
    if (dom.modeTrainingBtn) {
      dom.modeTrainingBtn.addEventListener('click', () => setOptimizerMode('training'));
    }
    if (dom.modeInferenceBtn) {
      dom.modeInferenceBtn.addEventListener('click', () => setOptimizerMode('inference'));
    }
    if (dom.autoGenerateCheckbox) {
      dom.autoGenerateCheckbox.addEventListener('change', () => {
        state.autoGenerate = dom.autoGenerateCheckbox.checked;
        updatePauseButton();
      });
    }
    if (dom.toggleMergingBtn) {
      dom.toggleMergingBtn.addEventListener('click', toggleMerging);
    }
    dom.fitViewBtn.addEventListener('click', fitAllSites);

    const autoChangeCb = document.getElementById('autoChangeSites');
    if (autoChangeCb) {
      state.autoChangeSites = autoChangeCb.checked;
      autoChangeCb.addEventListener('change', () => {
        state.autoChangeSites = autoChangeCb.checked;
      });
    }
    
    function setHistoryHover(hovered) {
      if (state.historyHovered === hovered) return;
      state.historyHovered = hovered;
      animateHistoryHover();
    }

    function animateHistoryHover() {
      if (state.historyHoverAnimFrame) {
        cancelAnimationFrame(state.historyHoverAnimFrame);
        state.historyHoverAnimFrame = null;
      }
      let lastTime = performance.now();
      const duration = 200; // 0.2s transition

      function frame(now) {
        const dt = now - lastTime;
        lastTime = now;
        const target = state.historyHovered ? 1.0 : 0.0;
        const diff = target - state.historyHoverFactor;
        
        if (Math.abs(diff) < 0.005) {
          state.historyHoverFactor = target;
          drawHistory();
          state.historyHoverAnimFrame = null;
          return;
        }
        
        const step = (dt / duration) * (diff > 0 ? 1 : -1);
        if (Math.abs(step) >= Math.abs(diff)) {
          state.historyHoverFactor = target;
          drawHistory();
          state.historyHoverAnimFrame = null;
        } else {
          state.historyHoverFactor += step;
          drawHistory();
          state.historyHoverAnimFrame = requestAnimationFrame(frame);
        }
      }
      state.historyHoverAnimFrame = requestAnimationFrame(frame);
    }

    if (dom.historyCanvas) {
      dom.historyCanvas.addEventListener('click', () => {
        if (state.scoreHistory.length > 100) {
          state.showFullHistory = !state.showFullHistory;
          drawHistory();
        }
      });
      dom.historyCanvas.addEventListener('pointerenter', () => setHistoryHover(true));
      dom.historyCanvas.addEventListener('pointerleave', () => setHistoryHover(false));
      dom.historyCanvas.style.cursor = 'default';
    }

    const trendSection = document.querySelector('.trend-section');
    if (trendSection) {
      trendSection.addEventListener('pointerenter', () => setHistoryHover(true));
      trendSection.addEventListener('pointerleave', () => setHistoryHover(false));
    }
  }

  function setupPanelEvents() {
    dom.panelToggle.addEventListener('click', () => setPanelOpen(true));
    dom.panelClose.addEventListener('click', () => setPanelOpen(false));
    dom.panelScrim.addEventListener('click', () => setPanelOpen(false));
    document.addEventListener('keydown', handlePanelKeydown);
    document.addEventListener('keydown', handleGlobalKeydown);
    const handlePanelModeChange = () => setPanelOpen(false);
    if (typeof panelMediaQuery.addEventListener === 'function') {
      panelMediaQuery.addEventListener('change', handlePanelModeChange);
    } else {
      panelMediaQuery.addListener(handlePanelModeChange);
    }
    syncPanelAccessibility();
  }

  function setupDeveloperEvents() {
    if (!dom.developerPanel || !dom.developerToggle || !dom.developerClose) return;
    dom.developerToggle.addEventListener('click', () => {
      setDeveloperPanelOpen(!state.developerOpen);
    });
    dom.developerClose.addEventListener('click', () => setDeveloperPanelOpen(false));
  }

  function setDeveloperPanelOpen(open) {
    if (!dom.developerPanel || !dom.developerToggle) return;
    const nextOpen = Boolean(open);
    if (nextOpen === state.developerOpen) return;

    if (nextOpen && document.activeElement instanceof HTMLElement) {
      developerReturnFocus = document.activeElement;
    }
    state.developerOpen = nextOpen;
    dom.developerPanel.hidden = !nextOpen;
    dom.developerToggle.setAttribute('aria-expanded', String(nextOpen));
    document.body.dataset.developerOpen = String(nextOpen);

    if (nextOpen) {
      state.debugScoreSignature = null;
      updateDeveloperPanel();
      window.requestAnimationFrame(() => {
        drawDebugScoreHistory();
        dom.developerPanel.focus({ preventScroll: true });
      });
      return;
    }

    if (state.developerUpdateFrame !== null) {
      window.cancelAnimationFrame(state.developerUpdateFrame);
      state.developerUpdateFrame = null;
    }

    if (developerReturnFocus instanceof HTMLElement && document.contains(developerReturnFocus)) {
      developerReturnFocus.focus({ preventScroll: true });
    } else {
      dom.developerToggle.focus({ preventScroll: true });
    }
    developerReturnFocus = null;
  }

  function setPanelOpen(open) {
    const overlayMode = panelMediaQuery.matches;
    const nextOpen = overlayMode && Boolean(open);
    const activeElement = document.activeElement;
    const focusWasInside = dom.controlsPanel.contains(activeElement);
    if (nextOpen && activeElement instanceof HTMLElement) panelReturnFocus = activeElement;

    let returnTarget = null;
    if (!nextOpen && overlayMode && (focusWasInside || panelReturnFocus)) {
      returnTarget = panelReturnFocus instanceof HTMLElement && document.contains(panelReturnFocus)
        ? panelReturnFocus
        : dom.panelToggle;
      panelReturnFocus = null;
      returnTarget.focus({ preventScroll: true });
    }

    dom.controlsPanel.dataset.open = String(nextOpen);
    syncPanelAccessibility();
    if (!overlayMode) panelReturnFocus = null;

    if (nextOpen) {
      dom.panelClose.focus({ preventScroll: true });
    }
  }

  function syncPanelAccessibility() {
    const overlayMode = panelMediaQuery.matches;
    const open = overlayMode && dom.controlsPanel.dataset.open === 'true';
    dom.panelToggle.setAttribute('aria-expanded', String(open));
    document.body.dataset.panelOpen = String(open);

    if (overlayMode) {
      dom.controlsPanel.inert = !open;
      dom.controlsPanel.setAttribute('aria-hidden', String(!open));
      dom.controlsPanel.setAttribute('role', 'dialog');
      dom.controlsPanel.setAttribute('aria-modal', 'true');
    } else {
      dom.controlsPanel.inert = false;
      dom.controlsPanel.removeAttribute('aria-hidden');
      dom.controlsPanel.removeAttribute('role');
      dom.controlsPanel.removeAttribute('aria-modal');
    }
  }

  function handlePanelKeydown(event) {
    if (!panelMediaQuery.matches || dom.controlsPanel.dataset.open !== 'true') return;
    if (event.key === 'Escape') {
      event.preventDefault();
      setPanelOpen(false);
      return;
    }
    if (event.key !== 'Tab') return;

    const focusable = [...dom.controlsPanel.querySelectorAll(
      'button:not([disabled]), select:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])'
    )].filter((element) => !element.hidden && element.getClientRects().length > 0);
    if (!focusable.length) {
      event.preventDefault();
      dom.controlsPanel.focus({ preventScroll: true });
      return;
    }

    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const active = document.activeElement;
    if (event.shiftKey && (active === first || !dom.controlsPanel.contains(active))) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (active === last || !dom.controlsPanel.contains(active))) {
      event.preventDefault();
      first.focus();
    }
  }

  function handleGlobalKeydown(event) {
    const debugShortcut =
      (event.ctrlKey || event.metaKey) &&
      event.shiftKey &&
      !event.altKey &&
      (event.code === 'KeyD' || event.key.toLowerCase() === 'd');
    if (debugShortcut) {
      event.preventDefault();
      setDeveloperPanelOpen(!state.developerOpen);
      return;
    }

    const active = document.activeElement;
    if (
      active &&
      (active.tagName === 'INPUT' ||
       active.tagName === 'SELECT' ||
       active.tagName === 'TEXTAREA' ||
       active.isContentEditable)
    ) {
      return;
    }

    if (event.key === 'Escape' && state.developerOpen) {
      event.preventDefault();
      setDeveloperPanelOpen(false);
      return;
    }

    if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) {
      return;
    }

    let handled = true;
    const key = event.key.toLowerCase();
    if (event.code === 'KeyP' || key === 'p' || key === 'з' || event.code === 'Space' || key === ' ' || key === 'spacebar') {
      if ((key === ' ' || key === 'spacebar' || event.code === 'Space') && active && active.tagName === 'BUTTON') {
        return;
      }
      toggleTraining();
    } else if (key === 'n' || key === 'т') {
      requestNewSite();
    } else if (key === 'b' || key === 'и') {
      const select = dom.boundaryType || document.getElementById('boundaryType');
      if (select && select.options.length > 0) {
        const nextIndex = (select.selectedIndex + 1) % select.options.length;
        select.selectedIndex = nextIndex;
        select.dispatchEvent(new Event('change'));
      }
    } else if (event.code === 'KeyM' || key === 'm' || key === 'ь') {
      toggleMerging();
    } else if (key === 'r' || key === 'к') {
      resetPolicy();
    } else if (key === 's' || key === 'ы') {
      saveCheckpoint();
    } else if (key === 'l' || key === 'д') {
      loadCheckpoint();
    } else if (event.code === 'KeyF' || key === 'f' || key === 'а') {
      state.showSDFGrid = !state.showSDFGrid;
      showToast(`SDF Grid Overlay: ${state.showSDFGrid ? 'ON' : 'OFF'}`);
      requestRender();
    } else {
      handled = false;
    }

    if (handled) {
      event.preventDefault();
    }
  }

  function setOptimizerMode(newMode) {
    if (!state.connected || state.mode === newMode) return;
    
    if (newMode === 'inference') {
      if (state.trainingWanted) {
        state.trainingWanted = false;
        clearTimeout(state.stepTimer);
        clearTimeout(state.transitionTimer);
      }
      sendCommand({ cmd: 'saveCheckpoint' });
      sendCommand({ cmd: 'setMode', mode: 'inference' });
      state.mode = 'inference';
      if (dom.modeTrainingBtn) {
        dom.modeTrainingBtn.classList.remove('active');
        dom.modeTrainingBtn.setAttribute('aria-checked', 'false');
      }
      if (dom.modeInferenceBtn) {
        dom.modeInferenceBtn.classList.add('active');
        dom.modeInferenceBtn.setAttribute('aria-checked', 'true');
      }
      if (dom.inferenceOptions) dom.inferenceOptions.style.display = 'block';
      requestNewSite();
      updatePauseButton();
      updateActionAvailability();
      showToast('Switched to Inference Mode · weights saved & history recording active');
    } else if (newMode === 'training') {
      if (state.trainingWanted) {
        state.trainingWanted = false;
        clearTimeout(state.stepTimer);
        clearTimeout(state.transitionTimer);
      }
      sendCommand({ cmd: 'setMode', mode: 'training' });
      state.mode = 'training';
      if (dom.modeTrainingBtn) {
        dom.modeTrainingBtn.classList.add('active');
        dom.modeTrainingBtn.setAttribute('aria-checked', 'true');
      }
      if (dom.modeInferenceBtn) {
        dom.modeInferenceBtn.classList.remove('active');
        dom.modeInferenceBtn.setAttribute('aria-checked', 'false');
      }
      if (dom.inferenceOptions) dom.inferenceOptions.style.display = 'none';
      requestNewSite();
      updatePauseButton();
      updateActionAvailability();
      showToast('Switched to Training Mode');
    }
  }

  function toggleTraining() {
    if (!state.connected || !state.hasSite || state.awaitingSite) return;

    state.trainingWanted = !state.trainingWanted;
    updatePauseButton();
    clearTimeout(state.stepTimer);
    clearTimeout(state.transitionTimer);

    if (!state.trainingWanted) {
      state.phase = state.stepInFlight ? 'pausing' : 'paused';
      const pauseMsg = state.mode === 'inference' ? 'Inference stopped' : 'Training paused';
      setProtocolStatus(state.stepInFlight ? 'Finishing current step' : pauseMsg);
      if (!state.stepInFlight) enterPausedState();
      return;
    }

    state.hoveredModuleId = null;
    state.lastHoveredModuleId = null;
    state.dimmingFactor = 0.0;

    cancelWallJob();
    if (state.pendingNextEpisode !== null) {
      beginNextEpisode();
    } else {
      state.phase = 'running';
      const activeMsg = state.mode === 'inference' ? (state.autoGenerate ? 'Auto-generating & streaming to dataset' : 'Inference active') : 'Training active';
      setProtocolStatus(activeMsg);
      scheduleNextStep(0);
      requestRender();
    }
  }

  function updatePauseButton() {
    const symbol = dom.pauseBtn.querySelector('.action-symbol');
    const title = dom.pauseBtn.querySelector('strong');
    const detail = dom.pauseBtn.querySelector('small');
    if (state.mode === 'inference') {
      if (state.trainingWanted) {
        symbol.textContent = 'Ⅱ';
        title.textContent = state.autoGenerate ? 'Stop Auto-Gen (Space)' : 'Pause (Space)';
        detail.textContent = state.phase === 'pausing' ? 'Finishing step' : 'Hold generation';
      } else {
        symbol.textContent = '▶';
        title.textContent = state.autoGenerate ? 'Auto Generate (Space)' : 'Generate (Space)';
        detail.textContent = state.autoGenerate ? 'Auto-stream to dataset' : 'Evaluate & record history';
      }
    } else {
      if (state.trainingWanted) {
        symbol.textContent = 'Ⅱ';
        title.textContent = 'Pause Training (Space)';
        detail.textContent = state.phase === 'pausing' ? 'Finishing step' : 'Hold training';
      } else {
        symbol.textContent = '▶';
        title.textContent = 'Start Training (Space)';
        detail.textContent = state.pendingNextEpisode !== null ? 'Start next episode' : 'Run learning';
      }
    }
    updateActionAvailability();
  }

  function updateActionAvailability() {
    const connected = state.connected;
    dom.pauseBtn.disabled = !connected || !state.hasSite || state.awaitingSite;
    dom.newSiteBtn.disabled = !connected || state.awaitingSite || state.settingsDirty;
    dom.loadCheckpointBtn.disabled = !connected || state.awaitingSite || state.settingsDirty;
    if (dom.toggleMergingBtn) {
      dom.toggleMergingBtn.disabled = !connected || !state.hasSite || state.trainingWanted;
    }

    if (state.mode === 'inference') {
      if (dom.saveCheckpointBtn) dom.saveCheckpointBtn.style.display = 'none';
      if (dom.resetPolicyBtn) dom.resetPolicyBtn.style.display = 'none';
      if (dom.panelConsoleKicker) dom.panelConsoleKicker.textContent = 'Inference console';
    } else {
      if (dom.saveCheckpointBtn) {
        dom.saveCheckpointBtn.style.display = '';
        dom.saveCheckpointBtn.disabled = !connected;
      }
      if (dom.resetPolicyBtn) {
        dom.resetPolicyBtn.style.display = '';
        dom.resetPolicyBtn.disabled = !connected || state.awaitingSite || state.settingsDirty;
      }
      if (dom.panelConsoleKicker) dom.panelConsoleKicker.textContent = 'Training console';
    }
  }

  function applySettingsAndRefreshSite() {
    state.settingsTimer = null;
    const validation = readAndValidateSettings();
    if (!validation.ok) return;
    state.settings = validation.settings;
    state.settingsDirty = true;
    if (!state.connected) return;
    if (state.awaitingSite) {
      setProtocolStatus('Settings queued for the next generation');
      return;
    }
    applySettingsTransaction('Applying settings to all environments');
  }

  function applySettingsTransaction(reason) {
    if (!state.connected) return;
    const validation = readAndValidateSettings();
    if (!validation.ok) return;

    state.settings = copySettings(validation.settings);
    state.pendingSettings = copySettings(validation.settings);
    state.settingsDirty = false;
    prepareForSiteRequest(reason);
    if (!sendCommand({ cmd: 'updateSettings', settings: state.pendingSettings })) {
      state.pendingSettings = null;
      state.settingsDirty = true;
      recoverFailedSiteRequest('Settings were not sent · waiting for the connection');
    }
  }

  function requestNewSite() {
    if (!state.connected || state.awaitingSite) return;
    if (state.settingsDirty) {
      applySettingsTransaction('Applying settings to a new generation');
      return;
    }
    prepareForSiteRequest('Generating a new family of sites');
    if (!sendCommand({ cmd: 'newSite' })) {
      recoverFailedSiteRequest('New site request was not sent · waiting for the connection');
    }
  }

  function prepareForSiteRequest(reason) {
    clearTimeout(state.stepTimer);
    clearTimeout(state.transitionTimer);
    state.stepInFlight = false;
    state.awaitingSite = true;
    state.pendingNextEpisode = null;
    state.pendingNextDictionary = null;
    state.phase = 'loading';
    cancelWallJob();
    updateActionAvailability();
    setProtocolStatus(reason);
    showCanvasMessage(reason, 'Keeping the current drawing visible until the new generation is ready.');
  }

  function resetPolicy() {
    if (!state.connected || state.awaitingSite || state.settingsDirty) return;
    dom.resetConfirmModal.style.display = 'flex';
  }

  function hideResetConfirmation() {
    dom.resetConfirmModal.style.display = 'none';
  }

  function confirmResetPolicy() {
    hideResetConfirmation();
    const validation = readAndValidateSettings();
    if (!validation.ok) return;

    state.settings = validation.settings;
    state.scoreHistory = [];
    state.bestScore = 0;
    state.serverMetrics = {};
    state.debugTelemetry = {};
    state.debugScoreSignature = null;
    drawHistory();
    updateDeveloperPanel();
    prepareForSiteRequest('Resetting policy weights');
    state.settingsDirty = false;
    if (!sendCommand({ cmd: 'resetPolicy' })) {
      recoverFailedSiteRequest('Reset request was not sent · waiting for the connection');
    }
  }

  function recoverFailedSiteRequest(reason) {
    state.awaitingSite = false;
    state.phase = state.hasSite
      ? (state.trainingWanted ? 'running' : 'paused')
      : 'disconnected';
    updateActionAvailability();
    setProtocolStatus(reason);
    if (state.hasSite) hideCanvasMessage();
    requestRender();
  }

  function saveCheckpoint() {
    if (!state.connected) return;
    sendCommand({ cmd: 'saveCheckpoint' });
    if (!state.trainingWanted) {
      setProtocolStatus('Saving policy checkpoint');
    } else {
      showToast('Saving policy checkpoint in background...');
    }
  }

  function loadCheckpoint() {
    if (!state.connected || state.awaitingSite || state.settingsDirty) return;
    dom.weightFileInput.value = '';
    dom.weightFileInput.click();
  }

  function handleWeightFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;

    const isTraining = state.trainingWanted;
    if (!isTraining) {
      prepareForSiteRequest('Loading policy checkpoint');
    } else {
      showToast('Loading policy checkpoint...');
    }

    const reader = new FileReader();
    reader.onload = function(e) {
      const arrayBuffer = e.target.result;
      const bytes = new Uint8Array(arrayBuffer);
      let binary = '';
      const len = bytes.byteLength;
      for (let i = 0; i < len; i++) {
        binary += String.fromCharCode(bytes[i]);
      }
      const base64 = btoa(binary);
      if (!sendCommand({ cmd: 'loadCheckpoint', fileData: base64 })) {
        if (!isTraining) {
          recoverFailedSiteRequest('Load request was not sent · waiting for the connection');
        } else {
          showToast('Failed to send load request', 'error');
        }
      }
    };
    reader.onerror = function() {
      if (!isTraining) {
        recoverFailedSiteRequest('Failed to read the selected file');
      }
      showToast('Error reading the checkpoint file', 'error');
    };
    reader.readAsArrayBuffer(file);
  }

  function buildWebSocketUrl() {
    const secure = window.location.protocol === 'https:';
    const scheme = secure ? 'wss:' : 'ws:';
    const queryOverride = new URLSearchParams(window.location.search).get('ws');
    if (queryOverride) {
      try {
        const overrideUrl = new URL(queryOverride, window.location.href);
        if (overrideUrl.protocol === 'ws:' || overrideUrl.protocol === 'wss:') return overrideUrl.href;
      } catch (_error) {
        // Ignore malformed optional overrides and use the derived local endpoint.
      }
    }
    const origin = window.location.origin && window.location.origin !== 'null'
      ? window.location.origin
      : 'http://127.0.0.1:8000';
    const endpoint = new URL('/ws', origin);
    endpoint.protocol = scheme;
    return endpoint.href;
  }

  function connectWebSocket() {
    clearTimeout(state.reconnectTimer);
    state.socketSerial += 1;
    const serial = state.socketSerial;
    state.connectionState = 'connecting';
    updateConnectionUI('connecting', state.reconnectAttempt ? `Reconnecting · attempt ${state.reconnectAttempt + 1}` : 'Connecting');

    let socket;
    try {
      socket = new WebSocket(buildWebSocketUrl());
    } catch (error) {
      handleSocketUnavailable(error);
      return;
    }

    state.socket = socket;

    socket.addEventListener('open', () => {
      if (serial !== state.socketSerial) return;
      state.connected = true;
      state.reconnectAttempt = 0;
      state.connectionState = 'connected';
      updateConnectionUI('connected', 'Connected');
      updateActionAvailability();
      applySettingsTransaction(state.hasSite ? 'Synchronizing after reconnect' : 'Preparing parallel environments');
    });

    socket.addEventListener('message', (event) => {
      if (serial !== state.socketSerial) return;
      handleSocketMessage(event.data);
    });

    socket.addEventListener('error', () => {
      if (serial !== state.socketSerial) return;
      updateConnectionUI('error', 'Connection error');
    });

    socket.addEventListener('close', () => {
      if (serial !== state.socketSerial) return;
      state.connected = false;
      state.connectionState = 'disconnected';
      state.stepInFlight = false;
      clearTimeout(state.stepTimer);
      clearTimeout(state.transitionTimer);
      updateConnectionUI('disconnected', 'Backend offline');
      updateActionAvailability();
      setProtocolStatus('Waiting to reconnect');
      if (!state.hasSite) {
        showCanvasMessage('Backend is offline', 'Reconnect is automatic. Start the optimizer server if it is not running.', 'error');
      } else {
        showToast('Connection lost. The current plan is preserved while reconnecting.', 'error');
      }
      if (!state.manuallyClosed) scheduleReconnect();
    });
  }

  function handleSocketUnavailable(error) {
    state.connected = false;
    updateConnectionUI('error', 'WebSocket unavailable');
    showCanvasMessage('Unable to open a live connection', error.message || 'This browser could not create a WebSocket.', 'error');
    scheduleReconnect();
  }

  function scheduleReconnect() {
    clearTimeout(state.reconnectTimer);
    const base = Math.min(15000, 500 * (2 ** state.reconnectAttempt));
    const jitter = Math.round(base * 0.12 * Math.random());
    const delay = base + jitter;
    state.reconnectAttempt += 1;
    state.reconnectTimer = window.setTimeout(connectWebSocket, delay);
  }

  function sendCommand(payload) {
    if (!state.socket || state.socket.readyState !== WebSocket.OPEN) return false;
    try {
      state.socket.send(JSON.stringify(payload));
      return true;
    } catch (error) {
      showToast(`Command could not be sent: ${error.message}`, 'error');
      return false;
    }
  }

  function updateConnectionUI(connectionState, text) {
    state.connectionState = connectionState;
    dom.connectionBadge.dataset.state = connectionState;
    dom.connectionText.textContent = text;
  }

  function handleSocketMessage(rawMessage) {
    let data;
    try {
      data = JSON.parse(rawMessage);
    } catch (_error) {
      showToast('The backend sent an unreadable message.', 'error');
      return;
    }

    if (!data || typeof data.type !== 'string') {
      showToast('The backend sent a message without a type.', 'error');
      return;
    }

    captureDebugEnvelope(data);

    switch (data.type) {
      case 'site':
        handleSiteEvent(data);
        break;
      case 'placements':
        handlePlacementsEvent(data);
        break;
      case 'episodeDone':
        handleEpisodeDoneEvent(data);
        break;
      case 'ack':
        handleAckEvent(data);
        break;
      case 'error':
        handleErrorEvent(data);
        break;
      default:
        showToast(`Unknown backend event: ${data.type}`, 'error');
    }
  }

  function captureDebugEnvelope(data) {
    const metrics = data && data.metrics && typeof data.metrics === 'object' ? data.metrics : {};
    const aggregate = metricRoot(metrics);
    const diagnostics = firstDefined(
      data.diagnostics,
      metrics.runtimeDiagnostics,
      aggregate.runtimeDiagnostics,
      metrics.diagnostics,
      aggregate.diagnostics
    );
    const diagnosticObject = diagnostics && typeof diagnostics === 'object' ? diagnostics : {};
    const nativeStatus = firstDefined(
      diagnosticObject.nativeGeometry,
      diagnosticObject.nativeGeometryStatus,
      data.nativeGeometry,
      data.nativeGeometryStatus,
      metrics.nativeGeometry,
      metrics.nativeGeometryStatus,
      aggregate.nativeGeometry,
      aggregate.nativeGeometryStatus
    );
    if (nativeStatus !== undefined) state.nativeGeometryTelemetry = sanitizeNativeTelemetry(nativeStatus);

    const memory = firstDefined(
      diagnosticObject.memory,
      diagnosticObject.memoryUsage,
      diagnosticObject.processMemory,
      hasMemoryTelemetry(diagnosticObject) ? diagnosticObject : undefined,
      data.memory,
      data.memoryUsage,
      data.processMemory,
      metrics.memory,
      metrics.memoryUsage,
      metrics.processMemory,
      aggregate.memory,
      aggregate.memoryUsage,
      aggregate.processMemory
    );
    if (memory !== undefined) state.memoryTelemetry = sanitizeMemoryTelemetry(memory);
    const diagnosticDevice = firstDefined(diagnosticObject.device, diagnosticObject.accelerator);
    if (typeof diagnosticDevice === 'string' && diagnosticDevice) state.device = diagnosticDevice;

    const nextTelemetry = { ...state.debugTelemetry };
    for (const key of DEBUG_METRIC_KEYS) {
      const value = firstDefined(aggregate[key], metrics[key]);
      if (value !== undefined && (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean')) {
        nextTelemetry[key] = value;
      }
    }
    const timings = firstDefined(aggregate.performanceTimings, metrics.performanceTimings);
    if (timings && typeof timings === 'object') {
      const boundedTimings = {};
      for (const key of DEBUG_TIMING_KEYS) {
        const record = timings[key];
        if (!record || typeof record !== 'object') continue;
        boundedTimings[key] = {
          avg: finiteOr(record.avg, 0),
          min: finiteOr(record.min, 0),
          max: finiteOr(record.max, 0),
          count: Math.max(0, Math.round(finiteOr(record.count, 0)))
        };
      }
      if (Object.keys(boundedTimings).length) nextTelemetry.performanceTimings = boundedTimings;
    }
    state.debugTelemetry = nextTelemetry;
  }

  function handleSiteEvent(data) {
    if (data.generationId === undefined || data.generationId === null) {
      showToast('Site event is missing its generation identifier.', 'error');
      return;
    }

    state.settingsDirty = false;
    state.generationId = data.generationId;
    state.episode = data.episode ?? 0;
    state.pendingNextEpisode = null;
    state.pendingNextDictionary = null;
    state.step = 0;
    state.stepInFlight = false;
    state.awaitingSite = false;
    state.hasSite = true;
    state.phase = state.trainingWanted ? 'running' : 'paused';
    state.device = typeof data.device === 'string' ? data.device : null;
    state.serverMetrics = data.metrics || {};
    state.dictionary = Array.isArray(data.dictionary) ? data.dictionary : [];

    if (Array.isArray(data.scoreHistory)) state.scoreHistory = boundedScoreHistory(data.scoreHistory);
    if (data.bestScore !== undefined) {
      state.bestScore = Number(data.bestScore) || 0;
    }
    drawHistory();

    state.boundaries = normalizeBoundaries(data.boundaries);
    state.boundaryByInstance = new Map(state.boundaries.map((boundary) => [String(boundary.instanceIdx), boundary]));
    state.totalSiteArea = state.boundaries.reduce((total, boundary) => total + boundary.siteArea, 0);
    clearPlacementState();
    state.individualPlacementsList = [];
    state.currentMergedPlacements = [];

    dom.deviceBadge.textContent = state.device ? `Device ${state.device.toUpperCase()}` : 'Device —';
    hideCanvasMessage();
    updateDictionaryUI();
    updateMetricsUI();
    updateActionAvailability();
    updatePauseButton();
    fitAllSites();
    requestRender();

    if (state.trainingWanted) {
      setProtocolStatus('Generation ready · training active');
      scheduleNextStep(80);
    } else {
      enterPausedState();
    }
  }

  function normalizeBoundaries(boundaries) {
    if (!Array.isArray(boundaries)) return [];
    return boundaries.map((boundary, index) => {
      const outer = normalizePolygon(boundary && boundary.outer);
      const holes = Array.isArray(boundary && boundary.holes)
        ? boundary.holes.map(normalizePolygon).filter((polygon) => polygon.length >= 3)
        : [];
      const calculatedArea = Math.max(0, polygonArea(outer) - holes.reduce((sum, hole) => sum + polygonArea(hole), 0));
      return {
        instanceIdx: boundary && boundary.instanceIdx !== undefined ? boundary.instanceIdx : index,
        outer,
        holes,
        siteArea: finiteOr(boundary && boundary.siteArea, calculatedArea),
        bounds: polygonBounds(outer)
      };
    }).filter((boundary) => boundary.outer.length >= 3);
  }

  function handlePlacementsEvent(data) {
    if (!isCurrentRunEvent(data, data.episode)) return;
    state.stepInFlight = false;
    clearTimeout(state.stepTimer);
    state.step = Number.isFinite(Number(data.step)) ? Number(data.step) : state.step + 1;

    if (!state.individualPlacementsList) {
      state.individualPlacementsList = [];
    }
    if (Array.isArray(data.placements)) {
      state.individualPlacementsList.push(...data.placements);
    }
    state.currentMergedPlacements = data.mergedPlacements || [];
    if (Array.isArray(data.mergedDictionary)) {
      state.mergedDictionary = data.mergedDictionary;
    }
    if (Array.isArray(data.dictionary)) {
      state.currentDictionary = data.dictionary;
    }

    state.serverMetrics = data.metrics || state.serverMetrics;
    updateMetricsUI();
    scheduleAccessibleSiteMetrics();

    if (state.trainingWanted) {
      state.phase = 'running';
      state.hoveredModuleId = null;
      state.lastHoveredModuleId = null;
      state.dimmingFactor = 0.0;
      if (Array.isArray(data.placements)) {
        for (const placement of data.placements) upsertPlacement(placement);
      }
      updateDictionaryUI();
      setProtocolStatus(`Episode ${state.episode} · step ${state.step}`);
      scheduleNextStep();
    } else {
      if (state.phase !== 'paused') {
        enterPausedState();
      }
    }
    requestRender();
  }

  function handleEpisodeDoneEvent(data) {
    if (!isCurrentRunEvent(data, data.completedEpisode)) return;
    state.stepInFlight = false;
    clearTimeout(state.stepTimer);
    clearTimeout(state.transitionTimer);
    state.phase = 'complete';
    state.serverMetrics = data.metrics || state.serverMetrics;
    state.pendingNextEpisode = data.nextEpisode ?? incrementEpisode(data.completedEpisode);
    state.pendingNextDictionary = Array.isArray(data.nextDictionary) ? data.nextDictionary : null;
    
    state.individualPlacementsList = data.placements || [];
    state.currentMergedPlacements = data.mergedPlacements || [];

    if (Array.isArray(data.dictionary)) state.dictionary = data.dictionary;
    if (Array.isArray(data.mergedDictionary)) state.mergedDictionary = data.mergedDictionary;
    if (Array.isArray(data.scoreHistory)) state.scoreHistory = boundedScoreHistory(data.scoreHistory);
    state.bestScore = finiteOr(data.bestScore, state.bestScore);

    reloadPausedPlacements();

    updateDictionaryUI();
    updateMetricsUI();
    drawHistory();

    if (state.mode === 'inference') {
      if (!state.autoGenerate) {
        state.trainingWanted = false;
        state.phase = 'paused';
        updatePauseButton();
        setProtocolStatus(`Generation ${data.completedEpisode} complete · saved to dataset`);
        showToast(`Generation complete (Score: ${Number(data.metrics?.score || 0).toFixed(1)}) · saved to data/dataset_v1.jsonl`);
        enterPausedState();
      } else {
        updatePauseButton();
        setProtocolStatus(`Auto-Gen ${data.completedEpisode} complete · streaming to dataset`);
        showToast(`Auto-Gen complete (Score: ${Number(data.metrics?.score || 0).toFixed(1)}) · saved to data/dataset_v1.jsonl`);
      }
    } else {
      updatePauseButton();
      setProtocolStatus(`Episode ${data.completedEpisode} complete · resolving vector walls`);
    }
    requestRender();

    scheduleWallCache(() => {
      if (state.mode === 'inference' && !state.autoGenerate) return;
      if (!state.trainingWanted || state.pendingNextEpisode === null || state.awaitingSite) return;
      state.transitionTimer = window.setTimeout(() => {
        if (!state.trainingWanted || state.awaitingSite) return;
        if (state.autoChangeSites || (state.mode === 'inference' && state.autoGenerate)) {
          state.pendingNextEpisode = null;
          requestNewSite();
        } else if (state.pendingNextEpisode !== null) {
          beginNextEpisode();
        }
      }, 650);
    });
  }

  function handleAckEvent(data) {
    const command = String(data.command || data.cmd || '').toLowerCase();
    const message = data.message || data.msg || '';
    if (command === 'updatesettings' && state.pendingSettings) {
      state.acceptedSettings = copySettings(state.pendingSettings);
      state.pendingSettings = null;
    }
    if (command.includes('save') || /checkpoint|saved/i.test(message)) {
      showToast(message || 'Policy checkpoint saved.');
      if (!state.trainingWanted) {
        setProtocolStatus('Checkpoint saved');
      }
    } else if (command.includes('reset') || /policy reset/i.test(message)) {
      showToast(message || 'Policy weights reset successfully.');
      setProtocolStatus('Weights reset');
    } else if (command.includes('load') || /checkpoint loaded/i.test(message)) {
      showToast(message || 'Policy checkpoint loaded successfully.');
      if (!state.trainingWanted) {
        setProtocolStatus('Weights loaded');
      }
    }
  }

  function handleErrorEvent(data) {
    const command = String(data.command || data.cmd || '').toLowerCase();
    const code = String(data.code || '').toLowerCase();
    const staleStep = command === 'step' && code === 'stale_generation';
    if (!staleStep && data.generationId !== undefined && state.generationId !== null && !sameToken(data.generationId, state.generationId)) return;
    if (!staleStep && data.episode !== undefined && state.episode !== null && !sameToken(data.episode, state.episode)) return;

    state.stepInFlight = false;
    clearTimeout(state.stepTimer);
    const message = data.message || 'The optimizer reported an error.';
    showToast(message, 'error');
    setProtocolStatus(`Error · ${message}`);

    if (data.recoverable !== false && code === 'invalid_settings' && command === 'updatesettings') {
      recoverRejectedSettings();
    } else if (data.recoverable !== false && staleStep) {
      resynchronizeAcceptedSettings('Step tokens changed · resynchronizing');
    } else if (data.recoverable !== false && command === 'step') {
      state.phase = state.trainingWanted ? 'running' : 'paused';
      updatePauseButton();
      updateActionAvailability();
      if (state.trainingWanted && state.hasSite && !state.awaitingSite) scheduleNextStep(80);
      else if (!state.trainingWanted) enterPausedState();
    } else if (data.recoverable === false) {
      state.awaitingSite = false;
      state.pendingSettings = null;
      state.trainingWanted = false;
      state.phase = 'error';
      updatePauseButton();
      updateActionAvailability();
      if (!state.hasSite) showCanvasMessage('Optimizer error', message, 'error');
      else hideCanvasMessage();
    } else if (state.awaitingSite && state.acceptedSettings) {
      resynchronizeAcceptedSettings('Request rejected · restoring the accepted generation');
    } else {
      state.awaitingSite = false;
      state.pendingSettings = null;
      state.phase = state.trainingWanted ? 'running' : 'paused';
      updatePauseButton();
      updateActionAvailability();
      if (state.trainingWanted && state.hasSite) scheduleNextStep(80);
      else if (!state.trainingWanted && state.hasSite) enterPausedState();
      else showCanvasMessage('Optimizer error', message, 'error');
    }
  }

  function recoverRejectedSettings() {
    const queuedSettings = state.settingsDirty;
    state.pendingSettings = null;
    if (!state.acceptedSettings) {
      state.awaitingSite = false;
      state.settingsDirty = true;
      state.phase = state.hasSite && state.trainingWanted ? 'running' : 'error';
      updatePauseButton();
      updateActionAvailability();
      if (state.hasSite && state.trainingWanted) scheduleNextStep(80);
      else if (!state.hasSite) showCanvasMessage('Settings were rejected', 'Correct the highlighted controls to create a site.', 'error');
      return;
    }

    if (!queuedSettings) {
      restoreSettingsControls(state.acceptedSettings);
      state.settingsDirty = false;
    }
    resynchronizeAcceptedSettings('Settings rejected · restoring last accepted values');
  }

  function resynchronizeAcceptedSettings(reason) {
    const accepted = copySettings(state.acceptedSettings);
    if (!accepted || !state.connected) {
      state.awaitingSite = false;
      state.pendingSettings = null;
      state.settingsDirty = true;
      updateActionAvailability();
      return;
    }

    prepareForSiteRequest(reason);
    state.pendingSettings = accepted;
    if (!sendCommand({ cmd: 'updateSettings', settings: accepted })) {
      state.pendingSettings = null;
      state.settingsDirty = true;
      recoverFailedSiteRequest('Resynchronization was not sent · waiting for the connection');
    }
  }

  function isCurrentRunEvent(data, eventEpisode) {
    if (state.awaitingSite || !state.hasSite) return false;
    if (!sameToken(data.generationId, state.generationId)) return false;
    if (!sameToken(eventEpisode, state.episode)) return false;
    return true;
  }

  function sameToken(left, right) {
    return left !== undefined && left !== null && right !== undefined && right !== null && String(left) === String(right);
  }

  function incrementEpisode(episode) {
    const number = Number(episode);
    return Number.isFinite(number) ? number + 1 : episode;
  }

  function beginNextEpisode() {
    if (!state.connected || state.awaitingSite || state.pendingNextEpisode === null) return;
    const nextEpisode = state.pendingNextEpisode;
    clearTimeout(state.transitionTimer);
    state.pendingNextEpisode = null;
    if (Array.isArray(state.pendingNextDictionary)) {
      state.dictionary = state.pendingNextDictionary;
    }
    state.pendingNextDictionary = null;
    state.episode = nextEpisode;
    state.step = 0;
    state.serverMetrics = { score: metricValue(state.serverMetrics, ['score'], 0) };
    clearPlacementState();
    state.phase = state.trainingWanted ? 'running' : 'paused';
    state.individualPlacementsList = [];
    state.currentMergedPlacements = [];
    state.mergedDictionary = [];

    state.hoveredModuleId = null;
    state.lastHoveredModuleId = null;
    state.dimmingFactor = 0.0;

    updateMetricsUI();
    updatePauseButton();
    requestRender();
    if (state.trainingWanted) {
      setProtocolStatus(`Episode ${state.episode} ready`);
      scheduleNextStep(80);
    } else {
      enterPausedState();
    }
  }

  function scheduleNextStep(delayOverride) {
    clearTimeout(state.stepTimer);
    if (!state.connected || !state.trainingWanted || !state.hasSite || state.awaitingSite || state.stepInFlight || state.pendingNextEpisode !== null) return;

    const interval = 1000 / clamp(state.speed, 1, 100);
    const elapsed = performance.now() - state.lastStepSentAt;
    const delay = delayOverride !== undefined ? delayOverride : Math.max(0, interval - elapsed);
    state.stepTimer = window.setTimeout(sendStep, delay);
  }

  function sendStep() {
    state.stepTimer = null;
    if (!state.connected || !state.trainingWanted || !state.hasSite || state.awaitingSite || state.stepInFlight || state.pendingNextEpisode !== null) return;
    state.stepInFlight = true;
    state.lastStepSentAt = performance.now();
    const sent = sendCommand({
      cmd: 'step',
      generationId: state.generationId,
      episode: state.episode
    });
    if (!sent) state.stepInFlight = false;
  }

  function reloadPausedPlacements() {
    const useMerged = !state.disableMerging;
    const list = useMerged ? state.currentMergedPlacements : state.individualPlacementsList;
    if (Array.isArray(list) && list.length > 0) {
      clearPlacementState();
      for (const placement of list) {
        upsertPlacement(placement);
      }
    }
  }

  function enterPausedState() {
    clearTimeout(state.stepTimer);
    state.phase = 'paused';
    const pausedMsg = state.mode === 'inference' ? 'Inference paused' : 'Training paused · resolving vector walls';
    setProtocolStatus(pausedMsg);
    updatePauseButton();
    updateMergingButton();
    if (Array.isArray(state.individualPlacementsList) && state.individualPlacementsList.length > 0) {
      reloadPausedPlacements();
    }
    updateDictionaryUI();
    
    // Request a complete terminal-like evaluation of the paused state
    sendCommand({
      cmd: 'evaluate',
      generationId: state.generationId,
      episode: state.episode
    });
    
    scheduleWallCache(() => setProtocolStatus(state.mode === 'inference' ? 'Inference paused' : 'Training paused · vector walls ready'));
  }

  function clearPlacementState() {
    state.placements.clear();
    state.placementOrder = [];
    state.graphEdges.clear();
    state.areasByInstance.clear();
    for (const boundary of state.boundaries) {
      state.areasByInstance.set(String(boundary.instanceIdx), { filled: 0, rentable: 0, modules: 0 });
    }
    state.totalFilledArea = 0;
    state.totalRentableArea = 0;
    state.placementRevision += 1;
    state.wallCache = null;
    cancelWallJob();
    clearTimeout(state.siteMetricTimer);
    state.siteMetricTimer = null;
    updateAccessibleSiteMetrics();
  }

  function upsertPlacement(rawPlacement) {
    if (!rawPlacement || !Array.isArray(rawPlacement.poly)) return;
    const poly = normalizePolygon(rawPlacement.poly);
    if (poly.length < 3) return;

    const instanceIdx = rawPlacement.instanceIdx ?? 0;
    const id = rawPlacement.id ?? `${state.step}-${state.placements.size}`;
    const key = placementKey(instanceIdx, id);
    const existing = state.placements.get(key);
    if (existing) removePlacementArea(existing);

    const module = rawPlacement.module || {};
    const category = CATEGORY_COLORS[module.category] ? module.category : 'room';
    const area = polygonArea(poly);
    const center = normalizePoint(rawPlacement.center) || polygonCentroid(poly);
    const bounds = polygonBounds(poly);

    const components = [];
    if (Array.isArray(rawPlacement.components)) {
      for (const comp of rawPlacement.components) {
        if (!comp || !Array.isArray(comp.poly)) continue;
        const compPoly = normalizePolygon(comp.poly);
        if (compPoly.length >= 3) {
          const compModule = comp.module || {};
          const compCategory = CATEGORY_COLORS[compModule.category] ? compModule.category : 'room';
          components.push({
            id: comp.id,
            poly: compPoly,
            category: compCategory,
            worldPath: createWorldPolygonPath(compPoly),
            center: polygonCentroid(compPoly),
            area: polygonArea(compPoly),
            module: {
              id: compModule.id || comp.id,
              category: compCategory
            }
          });
        }
      }
    }

    const placement = {
      id,
      key,
      instanceIdx,
      poly,
      bounds,
      worldPath: createWorldPolygonPath(poly),
      center,
      area,
      module: {
        id: module.id ?? id,
        category
      },
      neighbors: Array.isArray(rawPlacement.neighbors) ? rawPlacement.neighbors : [],
      components: components.length > 0 ? components : null
    };

    state.placements.set(key, placement);
    if (!existing) state.placementOrder.push(key);
    addPlacementArea(placement);

    for (const neighborId of placement.neighbors) {
      const normalizedNeighbor = neighborId && typeof neighborId === 'object' ? neighborId.id : neighborId;
      if (normalizedNeighbor === undefined || normalizedNeighbor === null) continue;
      const neighborKey = placementKey(instanceIdx, normalizedNeighbor);
      const edgeKey = graphEdgeKey(key, neighborKey);
      state.graphEdges.set(edgeKey, { a: key, b: neighborKey });
    }

    state.placementRevision += 1;
    state.wallCache = null;
    cancelWallJob();
  }

  function addPlacementArea(placement) {
    const instanceKey = String(placement.instanceIdx);
    const areaState = state.areasByInstance.get(instanceKey) || { filled: 0, rentable: 0, modules: 0 };
    areaState.filled += placement.area;
    areaState.modules += 1;
    state.totalFilledArea += placement.area;
    const rentableArea = placementRentableArea(placement);
    areaState.rentable += rentableArea;
    state.totalRentableArea += rentableArea;
    state.areasByInstance.set(instanceKey, areaState);
  }

  function placementRentableArea(placement) {
    if (Array.isArray(placement.components) && placement.components.length) {
      return placement.components.reduce((sum, component) => {
        return component.category === 'room' || component.category === 'special'
          ? sum + component.area
          : sum;
      }, 0);
    }
    return placement.module.category === 'room' || placement.module.category === 'special'
      ? placement.area
      : 0;
  }

  function removePlacementArea(placement) {
    const instanceKey = String(placement.instanceIdx);
    const areaState = state.areasByInstance.get(instanceKey);
    if (!areaState) return;
    areaState.filled = Math.max(0, areaState.filled - placement.area);
    areaState.modules = Math.max(0, areaState.modules - 1);
    state.totalFilledArea = Math.max(0, state.totalFilledArea - placement.area);
    const rentableArea = placementRentableArea(placement);
    areaState.rentable = Math.max(0, areaState.rentable - rentableArea);
    state.totalRentableArea = Math.max(0, state.totalRentableArea - rentableArea);
  }

  function placementKey(instanceIdx, id) {
    return `${String(instanceIdx)}:${String(id)}`;
  }

  function graphEdgeKey(a, b) {
    return a < b ? `${a}|${b}` : `${b}|${a}`;
  }

  function updateMetricsUI() {
    const metrics = metricRoot(state.serverMetrics);
    const fillRatio = state.totalSiteArea > 0 ? state.totalFilledArea / state.totalSiteArea : 0;
    const rentableRatio = state.totalFilledArea > 0 ? state.totalRentableArea / state.totalFilledArea : 0;
    const score = metricValue(metrics, ['score', 'averageScore', 'avgScore'], 0);
    const environmentCount = state.boundaries.length || (state.settings && state.settings.parallelEnvironments) || 0;
    if (Number.isFinite(score) && (state.phase === 'complete' || state.bestScore === 0)) {
      state.bestScore = Math.max(state.bestScore, score);
    }
    const serverBest = Number(metricValue(metrics, ['bestScore'], 0)) || 0;
    if (Number.isFinite(serverBest) && serverBest > 0) {
      state.bestScore = Math.max(state.bestScore, serverBest);
    }
    const best = state.bestScore;

    dom.scoreValue.textContent = formatDecimal(score, 1);
    const deepPen = Number(metricValue(metrics, ['deepInteriorPenalty'], 0)) || 0;
    const chasmPen = Number(metricValue(metrics, ['facadeChasmPenalty'], 0)) || 0;
    const topoPen = Number(metricValue(metrics, ['topologyPenalty'], 0)) || 0;
    if (deepPen > 0.05 || chasmPen > 0.05 || topoPen > 0.05) {
      dom.scoreValue.title = `Penalties: Deep Rooms: -${deepPen.toFixed(1)} pts | Facade Chasm (<3m): -${chasmPen.toFixed(1)} pts | Topology: -${topoPen.toFixed(1)} pts`;
    } else {
      dom.scoreValue.title = 'Score: No active penalties';
    }
    if (best !== 0 && !isNaN(parseFloat(best))) {
      dom.bestScoreValue.textContent = `Best ${formatDecimal(best, 1)}`;
    } else {
      dom.bestScoreValue.textContent = 'Best --';
    }
    dom.fillValue.textContent = formatPercent(fillRatio);
    dom.filledAreaValue.textContent = `${formatArea(state.totalFilledArea)} filled`;
    dom.rentableValue.textContent = formatPercent(rentableRatio);
    dom.episodeValue.textContent = padMetric(state.episode ?? 0);
    dom.environmentValue.textContent = `${environmentCount} ${environmentCount === 1 ? 'floor' : 'floors'}`;
    dom.stepValue.textContent = padMetric(state.step);
    dom.moduleCountValue.textContent = `${state.placements.size} ${state.placements.size === 1 ? 'module' : 'modules'}`;
    renderPerfTimings();
    scheduleDeveloperPanelUpdate();
  }

  function renderPerfTimings() {
    if (!dom.perfTimingsCard || !dom.perfTimingsDetails) return;
    const metrics = metricRoot(state.serverMetrics);
    const timings = metrics.performanceTimings;
    
    // Cache latest timings so they persist when paused
    if (timings && Object.keys(timings).length > 0) {
      state._lastPerfTimings = timings;
    }
    const t = state._lastPerfTimings;
    if (!t || Object.keys(t).length === 0) {
      dom.perfTimingsCard.style.display = 'none';
      return;
    }
    
    dom.perfTimingsCard.style.display = 'block';
    dom.perfTimingsDetails.replaceChildren();

    function fmtMs(v) {
      return v < 1 ? v.toFixed(3) : v < 100 ? v.toFixed(1) : Math.round(v).toString();
    }
    function humanLabel(key) {
      return key.replace(/([A-Z])/g, ' $1').replace(/^./, s => s.toUpperCase()).trim();
    }

    const table = document.createElement('table');
    table.style.cssText = 'width:100%;border-collapse:collapse;font-size:11px;font-family:var(--font-mono),monospace;';
    
    function addHeader() {
      const tr = document.createElement('tr');
      tr.style.cssText = 'color:#6d7970;font-size:9px;text-transform:uppercase;letter-spacing:0.5px;';
      for (const h of ['', 'Avg', 'Min', 'Max', 'N']) {
        const th = document.createElement('td');
        th.style.cssText = h === '' ? 'text-align:left;padding:2px 4px;' : 'text-align:right;padding:2px 6px;';
        th.textContent = h;
        tr.appendChild(th);
      }
      table.appendChild(tr);
    }

    function addRow(key, data, isTotal) {
      const tr = document.createElement('tr');
      if (isTotal) tr.style.cssText = 'font-weight:700;color:#c4db8b;font-size:12px;';
      const tdLabel = document.createElement('td');
      
      const isSubKey = key.startsWith('cg');
      const labelColor = isTotal ? '#c4db8b' : (isSubKey ? '#859288' : '#adb9b0');
      tdLabel.style.cssText = 'text-align:left;padding:3px 4px;color:' + labelColor + ';white-space:nowrap;';
      
      const humanLabels = {
        candidateGeneration: 'Candidate Generation',
        cgAnchorSearch: '  └ Anchor Search',
        cgOverlapCollisions: '  └ Overlap Collisions',
        cgSiteBoundary: '  └ Site Boundary',
        cgNeighborAnalysis: '  └ Neighbor & Overlap',
        cgEdgeAlignment: '  └ Edge Alignment',
        cgFeatureExtraction: '  └ Feature Extraction',
        policyInference: 'Policy Inference',
        shapeSynthesis: 'Shape Synthesis',
        placement: 'Placement',
        bpeMerge: 'BPE Merge',
        stepTotal: 'Step Total',
        terminalMetrics: 'Terminal Metrics',
        aggregateTerminal: 'Aggregate Terminal',
        episodeBpeMerge: 'Episode BPE Merge',
        learning: 'Learning',
        dictSynthesis: 'Dict Synthesis',
        episodeFormatting: 'Episode Formatting',
        episodeTotal: 'Episode Total',
      };
      
      const labelText = humanLabels[key] || humanLabel(key);
      if (isSubKey) {
        tdLabel.innerHTML = labelText.replace(/ /g, '&nbsp;');
      } else {
        tdLabel.textContent = labelText;
      }
      tr.appendChild(tdLabel);
      for (const val of [data.avg, data.min, data.max]) {
        const td = document.createElement('td');
        td.style.cssText = 'text-align:right;padding:3px 6px;color:' + (isTotal ? '#c4db8b' : (isSubKey ? '#859288' : '#dde3dd')) + ';';
        td.textContent = fmtMs(val) + 'ms';
        tr.appendChild(td);
      }
      const tdN = document.createElement('td');
      tdN.style.cssText = 'text-align:right;padding:3px 6px;color:#6d7970;font-size:10px;';
      tdN.textContent = data.count;
      tr.appendChild(tdN);
      table.appendChild(tr);
    }

    function addDivider() {
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = 5;
      td.style.cssText = 'padding:4px 0;';
      const hr = document.createElement('div');
      hr.style.cssText = 'height:1px;background:var(--panel-line);';
      td.appendChild(hr);
      tr.appendChild(td);
      table.appendChild(tr);
    }

    addHeader();
    const stepKeys = [
      'candidateGeneration',
      'cgAnchorSearch',
      'cgOverlapCollisions',
      'cgSiteBoundary',
      'cgNeighborAnalysis',
      'cgEdgeAlignment',
      'cgFeatureExtraction',
      'policyInference',
      'shapeSynthesis',
      'placement',
      'bpeMerge'
    ];
    const episodeKeys = ['terminalMetrics', 'aggregateTerminal', 'episodeBpeMerge', 'learning', 'dictSynthesis', 'episodeFormatting'];
    
    let addedStep = false;
    for (const key of stepKeys) {
      if (t[key]) { addRow(key, t[key], false); addedStep = true; }
    }
    if (t['stepTotal']) { addRow('stepTotal', t['stepTotal'], true); addedStep = true; }
    if (addedStep) addDivider();
    for (const key of episodeKeys) {
      if (t[key]) addRow(key, t[key], false);
    }
    if (t['episodeTotal']) addRow('episodeTotal', t['episodeTotal'], true);

    dom.perfTimingsDetails.appendChild(table);
  }

  function scheduleDeveloperPanelUpdate() {
    if (!state.developerOpen || state.developerUpdateFrame !== null) return;
    state.developerUpdateFrame = window.requestAnimationFrame(() => {
      state.developerUpdateFrame = null;
      updateDeveloperPanel();
    });
  }

  function updateDeveloperPanel() {
    if (!state.developerOpen || !dom.developerPanel) return;
    drawDebugScoreHistory();
    updateDebugRewardBreakdown();
    updateDebugRuntimeMetrics();
    updateDebugTrainingMetrics();
    updateDebugTimingRows();
  }

  function drawDebugScoreHistory() {
    const canvas = dom.debugScoreCanvas;
    if (!canvas || !state.developerOpen) return;
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(1, Math.round(rect.width || 620));
    const height = Math.max(1, Math.round(rect.height || 132));
    const values = state.scoreHistory.slice(-DEBUG_SCORE_POINT_LIMIT);
    const signatureSum = values.reduce((sum, value) => sum + value, 0);
    const signature = `${width}:${height}:${values.length}:${values[0] ?? ''}:${values.at(-1) ?? ''}:${signatureSum}`;
    if (signature === state.debugScoreSignature) return;
    state.debugScoreSignature = signature;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const retained = state.scoreHistory.length;
    dom.debugEpisodeMeta.textContent = retained
      ? `Showing ${values.length} of ${retained} retained episodes`
      : 'No completed episodes';

    if (!values.length) {
      canvas.setAttribute('aria-label', 'No episode scores have been reported');
      dom.debugScoreSummary.textContent = 'Waiting for the first completed episode.';
      ctx.fillStyle = '#7f8b82';
      ctx.font = '10px ui-sans-serif, system-ui, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('Episode scores will appear here', width / 2, height / 2 + 3);
      return;
    }

    const recent = values.slice(-Math.min(10, values.length));
    const last = values[values.length - 1];
    const best = Math.max(...values);
    const recentMean = recent.reduce((sum, value) => sum + value, 0) / recent.length;
    const delta = last - values[0];
    canvas.setAttribute(
      'aria-label',
      `${values.length} recent episode scores. Latest ${last.toFixed(2)}, best ${best.toFixed(2)}, change ${delta.toFixed(2)}.`
    );
    dom.debugScoreSummary.textContent =
      `Latest ${last.toFixed(2)} · best ${best.toFixed(2)} · recent mean ${recentMean.toFixed(2)} · window Δ ${delta >= 0 ? '+' : ''}${delta.toFixed(2)}`;

    const margin = { left: 40, right: 12, top: 11, bottom: 20 };
    const plotWidth = Math.max(1, width - margin.left - margin.right);
    const plotHeight = Math.max(1, height - margin.top - margin.bottom);
    const rawMin = Math.min(...values);
    const rawMax = Math.max(...values);
    const padding = Math.max(1, (rawMax - rawMin) * 0.12);
    const min = rawMin - padding;
    const max = rawMax + padding;
    const span = Math.max(1.0e-9, max - min);

    ctx.strokeStyle = 'rgba(255,255,255,0.07)';
    ctx.lineWidth = 1;
    for (const ratio of [0, 0.5, 1]) {
      const y = Math.round(margin.top + ratio * plotHeight) + 0.5;
      ctx.beginPath();
      ctx.moveTo(margin.left, y);
      ctx.lineTo(width - margin.right, y);
      ctx.stroke();
    }

    ctx.fillStyle = '#87948a';
    ctx.font = '9px ui-monospace, SFMono-Regular, Consolas, monospace';
    ctx.textAlign = 'right';
    ctx.fillText(rawMax.toFixed(1), margin.left - 6, margin.top + 4);
    ctx.fillText(rawMin.toFixed(1), margin.left - 6, height - margin.bottom + 3);

    const points = values.map((value, index) => ({
      x: margin.left + (values.length === 1 ? plotWidth : (index / (values.length - 1)) * plotWidth),
      y: margin.top + plotHeight - ((value - min) / span) * plotHeight
    }));
    const gradient = ctx.createLinearGradient(0, margin.top, 0, height - margin.bottom);
    gradient.addColorStop(0, 'rgba(196,219,139,0.28)');
    gradient.addColorStop(1, 'rgba(196,219,139,0.015)');
    ctx.beginPath();
    ctx.moveTo(points[0].x, height - margin.bottom);
    for (const point of points) ctx.lineTo(point.x, point.y);
    ctx.lineTo(points[points.length - 1].x, height - margin.bottom);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();

    ctx.beginPath();
    points.forEach((point, index) => index ? ctx.lineTo(point.x, point.y) : ctx.moveTo(point.x, point.y));
    ctx.strokeStyle = '#c4db8b';
    ctx.lineWidth = 1.8;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.stroke();
    if (points.length === 1) {
      ctx.beginPath();
      ctx.arc(points[0].x, points[0].y, 2.5, 0, Math.PI * 2);
      ctx.fillStyle = '#c4db8b';
      ctx.fill();
    }

    ctx.fillStyle = '#77837a';
    ctx.font = '9px ui-monospace, SFMono-Regular, Consolas, monospace';
    ctx.textAlign = 'left';
    ctx.fillText(`-${values.length - 1}`, margin.left, height - 5);
    ctx.textAlign = 'right';
    ctx.fillText('latest', width - margin.right, height - 5);
  }

  function updateDebugRewardBreakdown() {
    const target = dom.debugRewardBreakdown;
    if (!target) return;
    const metrics = state.debugTelemetry;
    const rewardKeys = [
      'fillRatio', 'rentableRatio', 'daylightRatio', 'reuseRatio',
      'constructibilityScore', 'envelopeEfficiency', 'rawScore',
      'topologyPenalty', 'bpeBonus', 'unmergedTrianglePenalty',
      'relativeTimeReward', 'dictBreachPenalty', 'deepInteriorPenalty',
      'facadeChasmPenalty'
    ];
    if (!rewardKeys.some((key) => Object.prototype.hasOwnProperty.call(metrics, key))) {
      target.replaceChildren(debugEmptyMessage('Reward components have not been reported yet.'));
      return;
    }

    const fillRatio = debugNumber('fillRatio');
    const rentableRatio = debugNumber('rentableRatio');
    const scaledFill = fillRatio < 0.6 ? Math.max(0, 2.25 * fillRatio - 0.75) : fillRatio;
    const scaledRentable = rentableRatio < 0.7 ? Math.max(0, (7 * rentableRatio - 2.8) / 3) : rentableRatio;
    const shapePenalty =
      debugNumber('areaVariancePenalty') +
      debugNumber('internalExposedPenalty') +
      debugNumber('partialConnectionPenalty');
    const components = [
      ['Space fill', scaledFill * 70],
      ['Rentable area', scaledRentable * 15],
      ['Daylight', debugNumber('daylightRatio') * 10],
      ['Vocabulary reuse', debugNumber('reuseRatio') * 2],
      ['Grid snapping', debugNumber('constructibilityScore') * 2],
      ['Envelope', debugNumber('envelopeEfficiency')],
      ['BPE reuse', debugNumber('bpeBonus')],
      ['Frontier shaping', debugNumber('relativeTimeReward')],
      ['Deep room penalty', -debugNumber('deepInteriorPenalty')],
      ['Facade chasm penalty', -debugNumber('facadeChasmPenalty')],
      ['Shape penalties', -shapePenalty],
      ['Topology penalty', -debugNumber('topologyPenalty')],
      ['Triangle penalty', -debugNumber('unmergedTrianglePenalty')],
      ['Dictionary penalty', -debugNumber('dictBreachPenalty')]
    ];
    const maxMagnitude = Math.max(1, ...components.map(([, value]) => Math.abs(value)));
    const fragment = document.createDocumentFragment();
    for (const [label, value] of components) {
      const row = document.createElement('div');
      row.className = 'developer-reward-row';
      const copy = document.createElement('div');
      copy.className = 'developer-reward-copy';
      const name = document.createElement('span');
      name.textContent = label;
      const amount = document.createElement('strong');
      amount.textContent = `${value > 0 ? '+' : ''}${value.toFixed(2)}`;
      amount.className = value < 0 ? 'is-negative' : 'is-positive';
      copy.append(name, amount);
      const track = document.createElement('span');
      track.className = 'developer-reward-track';
      const fill = document.createElement('i');
      fill.className = value < 0 ? 'is-negative' : 'is-positive';
      fill.style.width = `${Math.max(1.5, Math.abs(value) / maxMagnitude * 100)}%`;
      track.appendChild(fill);
      row.append(copy, track);
      fragment.appendChild(row);
    }

    const total = document.createElement('div');
    total.className = 'developer-reward-total';
    const totalLabel = document.createElement('span');
    totalLabel.textContent = 'Final score';
    const totalValue = document.createElement('strong');
    totalValue.textContent = formatOptionalNumber(metrics.score, 3);
    total.append(totalLabel, totalValue);
    fragment.appendChild(total);
    target.replaceChildren(fragment);
  }

  function updateDebugRuntimeMetrics() {
    if (!dom.debugRuntimeMetrics) return;
    const timings = state.debugTelemetry.performanceTimings || {};
    renderDebugMetricGrid(dom.debugRuntimeMetrics, [
      ['Device', state.device ? state.device.toUpperCase() : 'Not reported'],
      ['Native geometry', nativeGeometrySummary()],
      ['Candidates', formatOptionalInteger(state.debugTelemetry.candidateEvaluations)],
      ['Candidate avg', formatTimingAverage(timings.candidateGeneration)],
      ['Step avg', formatTimingAverage(timings.stepTotal)],
      ['Episode avg', formatTimingAverage(timings.episodeTotal)],
      ['Generation', formatSecondsAsMilliseconds(state.debugTelemetry.generationTimeSeconds)],
      ['Memory', memoryTelemetrySummary()]
    ]);
  }

  function updateDebugTrainingMetrics() {
    if (!dom.debugTrainingMetrics) return;
    const metrics = state.debugTelemetry;
    const algorithm = typeof metrics.learningAlgorithm === 'string'
      ? metrics.learningAlgorithm.replaceAll('_', ' ')
      : 'Not reported';
    renderDebugMetricGrid(dom.debugTrainingMetrics, [
      ['Algorithm', algorithm],
      ['Policy loss', formatOptionalNumber(metrics.policyLoss, 5)],
      ['Actor loss', formatOptionalNumber(metrics.actorLoss, 5)],
      ['Value loss', formatOptionalNumber(metrics.valueLoss, 5)],
      ['Entropy', formatOptionalNumber(metrics.policyEntropy, 5)],
      ['Advantage', formatOptionalNumber(metrics.advantage, 5)],
      ['Gradient norm', formatOptionalNumber(metrics.gradientNorm, 5)],
      ['Learning rate', formatOptionalNumber(metrics.learningRate, 6)],
      ['EMA baseline', formatOptionalNumber(metrics.baseline, 4)]
    ]);
  }

  function updateDebugTimingRows() {
    const target = dom.debugTimingRows;
    if (!target) return;
    const timings = state.debugTelemetry.performanceTimings || {};
    const available = DEBUG_TIMING_KEYS
      .filter((key) => timings[key] && Number.isFinite(Number(timings[key].avg)));
    if (!available.length) {
      target.replaceChildren(debugEmptyMessage('Profiler timings have not been reported yet.'));
      return;
    }

    const labels = {
      candidateGeneration: 'Candidate generation',
      policyInference: 'Policy inference',
      shapeSynthesis: 'Shape synthesis',
      placement: 'Placement commit',
      bpeMerge: 'Step BPE',
      stepTotal: 'Step total',
      terminalMetrics: 'Terminal metrics',
      aggregateTerminal: 'Aggregate score',
      episodeBpeMerge: 'Episode BPE',
      learning: 'Learning update',
      dictSynthesis: 'Dictionary synthesis',
      episodeFormatting: 'Protocol formatting',
      episodeTotal: 'Episode total'
    };
    const maxAverage = Math.max(0.001, ...available.map((key) => Number(timings[key].avg)));
    const fragment = document.createDocumentFragment();
    for (const key of available) {
      const timing = timings[key];
      const row = document.createElement('div');
      row.className = key === 'stepTotal' || key === 'episodeTotal'
        ? 'developer-timing-row is-total'
        : 'developer-timing-row';
      const heading = document.createElement('div');
      const label = document.createElement('span');
      label.textContent = labels[key] || key;
      const value = document.createElement('strong');
      value.textContent = `${formatMilliseconds(timing.avg)} avg · ${formatMilliseconds(timing.max)} max · n=${timing.count}`;
      heading.append(label, value);
      const track = document.createElement('span');
      track.className = 'developer-timing-track';
      const fill = document.createElement('i');
      fill.style.width = `${Math.max(1.5, Number(timing.avg) / maxAverage * 100)}%`;
      track.appendChild(fill);
      row.append(heading, track);
      fragment.appendChild(row);
    }
    target.replaceChildren(fragment);
  }

  function renderDebugMetricGrid(target, entries) {
    const fragment = document.createDocumentFragment();
    for (const [label, value] of entries) {
      const wrapper = document.createElement('div');
      const term = document.createElement('dt');
      const detail = document.createElement('dd');
      term.textContent = label;
      detail.textContent = value;
      wrapper.append(term, detail);
      fragment.appendChild(wrapper);
    }
    target.replaceChildren(fragment);
  }

  function debugEmptyMessage(message) {
    const empty = document.createElement('p');
    empty.className = 'developer-empty';
    empty.textContent = message;
    return empty;
  }

  function debugNumber(key) {
    return finiteOr(state.debugTelemetry[key], 0);
  }

  function formatOptionalNumber(value, digits) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return '—';
    if (numeric !== 0 && Math.abs(numeric) < 10 ** -digits) return numeric.toExponential(2);
    return numeric.toFixed(digits);
  }

  function formatOptionalInteger(value) {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? Math.round(numeric).toLocaleString() : '—';
  }

  function formatMilliseconds(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return '—';
    return numeric < 1 ? `${numeric.toFixed(3)} ms` : `${numeric.toFixed(1)} ms`;
  }

  function formatTimingAverage(record) {
    return record && Number.isFinite(Number(record.avg)) ? formatMilliseconds(record.avg) : '—';
  }

  function formatSecondsAsMilliseconds(value) {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? formatMilliseconds(numeric * 1000) : '—';
  }

  function formatBytes(value) {
    const bytes = Number(value);
    if (!Number.isFinite(bytes) || bytes < 0) return null;
    const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];
    let scaled = bytes;
    let unitIndex = 0;
    while (scaled >= 1024 && unitIndex < units.length - 1) {
      scaled /= 1024;
      unitIndex += 1;
    }
    const digits = scaled >= 100 || unitIndex === 0 ? 0 : scaled >= 10 ? 1 : 2;
    return `${scaled.toFixed(digits)} ${units[unitIndex]}`;
  }

  function memoryTelemetrySummary() {
    const memory = state.memoryTelemetry;
    if (typeof memory === 'string') return memory;
    if (typeof memory === 'number') return formatBytes(memory) || 'Not reported';
    if (!memory || typeof memory !== 'object') return 'Not reported';
    const rss = firstDefined(
      memory.processPeakRssBytes,
      memory.peakRssBytes,
      memory.rssObservedPeakBytes,
      memory.rssResourcePeakBytes,
      memory.rssBytes,
      memory.rss,
      memory.bytes
    );
    const accelerator = firstDefined(
      memory.peakAllocatedBytes,
      memory.acceleratorPeakBytes,
      memory.acceleratorAllocatedBytes,
      memory.allocatedBytes,
      memory.driverAllocatedBytes
    );
    const parts = [];
    const rssText = formatBytes(rss);
    const acceleratorText = formatBytes(accelerator);
    if (rssText) parts.push(`RSS ${rssText}`);
    if (acceleratorText) parts.push(`accelerator ${acceleratorText}`);
    return parts.length ? parts.join(' · ') : 'Not reported';
  }

  function nativeGeometrySummary() {
    const status = state.nativeGeometryTelemetry;
    if (typeof status === 'boolean') return status ? 'Enabled' : 'Python fallback';
    if (typeof status === 'string') return status;
    if (!status || typeof status !== 'object') return 'Not reported';
    const enabled = Boolean(status.enabled);
    const loaded = Boolean(firstDefined(status.loaded, status.available));
    const compatible = status.compatible;
    const backend = firstDefined(status.backend, status.library, status.name);
    if (enabled) return backend ? `Enabled · ${backend}` : 'Enabled';
    if (loaded && compatible !== false) return 'Loaded · disabled';
    if (status.reason || status.loadError) return `Fallback · ${status.reason || status.loadError}`;
    return loaded ? 'Loaded · incompatible' : 'Python fallback';
  }


  function scheduleAccessibleSiteMetrics() {
    if (state.siteMetricTimer !== null) return;
    const elapsed = performance.now() - state.lastSiteMetricUpdatedAt;
    state.siteMetricTimer = window.setTimeout(updateAccessibleSiteMetrics, Math.max(0, 600 - elapsed));
  }

  function updateAccessibleSiteMetrics() {
    clearTimeout(state.siteMetricTimer);
    state.siteMetricTimer = null;
    state.lastSiteMetricUpdatedAt = performance.now();
    dom.siteMetricList.replaceChildren();
    if (!state.boundaries.length) {
      const item = document.createElement('li');
      item.textContent = 'No floor sites are available yet.';
      dom.siteMetricList.appendChild(item);
      return;
    }

    const fragment = document.createDocumentFragment();
    state.boundaries.forEach((boundary, index) => {
      const area = state.areasByInstance.get(String(boundary.instanceIdx)) || { filled: 0, modules: 0 };
      const numericIndex = Number(boundary.instanceIdx);
      const floorNumber = Number.isFinite(numericIndex) ? numericIndex + 1 : index + 1;
      const item = document.createElement('li');
      item.textContent = `Floor ${floorNumber}: Net site area ${formatArea(boundary.siteArea)}; filled area ${formatArea(area.filled)}; ${area.modules || 0} modules.`;
      fragment.appendChild(item);
    });
    dom.siteMetricList.appendChild(fragment);
  }

  function metricRoot(metrics) {
    if (!metrics || typeof metrics !== 'object') return {};
    if (metrics.aggregate && typeof metrics.aggregate === 'object') return metrics.aggregate;
    return metrics;
  }

  function metricValue(metrics, keys, fallback) {
    const root = metricRoot(metrics);
    for (const key of keys) {
      const value = Number(root[key]);
      if (Number.isFinite(value)) return value;
    }
    return fallback;
  }

  function firstDefined(...values) {
    return values.find((value) => value !== undefined && value !== null);
  }

  function boundedScoreHistory(values) {
    if (!Array.isArray(values)) return [];
    return values
      .map(Number)
      .filter(Number.isFinite)
      .slice(-MAX_RETAINED_SCORE_HISTORY);
  }

  function hasMemoryTelemetry(value) {
    if (!value || typeof value !== 'object') return false;
    return [
      'rssBytes', 'rssObservedPeakBytes', 'rssResourcePeakBytes',
      'processPeakRssBytes', 'peakRssBytes', 'allocatedBytes',
      'peakAllocatedBytes', 'reservedBytes', 'peakReservedBytes',
      'acceleratorAllocatedBytes', 'acceleratorPeakBytes',
      'driverAllocatedBytes', 'tracemallocPeakBytes', 'bytes', 'rss'
    ].some((key) => value[key] !== undefined);
  }

  function sanitizeMemoryTelemetry(value) {
    if (typeof value === 'string' || typeof value === 'number') return value;
    if (!value || typeof value !== 'object') return null;
    const sanitized = {};
    for (const key of [
      'rssBytes', 'rssObservedPeakBytes', 'rssResourcePeakBytes',
      'processPeakRssBytes', 'peakRssBytes', 'allocatedBytes',
      'peakAllocatedBytes', 'reservedBytes', 'peakReservedBytes',
      'acceleratorAllocatedBytes', 'acceleratorPeakBytes',
      'driverAllocatedBytes', 'tracemallocPeakBytes', 'bytes', 'rss'
    ]) {
      const numeric = Number(value[key]);
      if (Number.isFinite(numeric) && numeric >= 0) sanitized[key] = numeric;
    }
    return Object.keys(sanitized).length ? sanitized : null;
  }

  function sanitizeNativeTelemetry(value) {
    if (typeof value === 'string' || typeof value === 'boolean') return value;
    if (!value || typeof value !== 'object') return null;
    const sanitized = {};
    for (const key of ['enabled', 'loaded', 'available', 'compatible']) {
      if (value[key] !== undefined) sanitized[key] = Boolean(value[key]);
    }
    for (const key of ['backend', 'library', 'name', 'path', 'reason', 'loadError']) {
      if (typeof value[key] === 'string') sanitized[key] = value[key].slice(0, 240);
    }
    return Object.keys(sanitized).length ? sanitized : null;
  }

  function updateDictionaryUI() {
    dom.dictionaryList.replaceChildren();
    
    // Count occurrences of each module ID in the current layout
    const counts = new Map();
    for (const key of state.placementOrder) {
      const placement = state.placements.get(key);
      if (!placement) continue;
      
      if (state.disableMerging && placement.components) {
        for (const comp of placement.components) {
          const compTypeId = (comp.module && comp.module.id) || comp.category;
          counts.set(compTypeId, (counts.get(compTypeId) || 0) + 1);
        }
      } else {
        const mid = placement.module.id;
        counts.set(mid, (counts.get(mid) || 0) + 1);
      }
    }

    const useMerged = !state.disableMerging;
    const basicList = (Array.isArray(state.currentDictionary) && state.currentDictionary.length > 0)
      ? state.currentDictionary
      : (Array.isArray(state.dictionary) ? state.dictionary : []);

    let rawList = [];
    if (useMerged && Array.isArray(state.mergedDictionary) && state.mergedDictionary.length > 0) {
      for (const merged of state.mergedDictionary) {
        const count = counts.get(merged.id) || 0;
        if (count >= 2) {
          rawList.push(merged);
        }
      }
      for (const base of basicList) {
        if (!rawList.some(m => m.id === base.id)) {
          rawList.push(base);
        }
      }
    } else {
      rawList = basicList;
    }

    let hasSpecialPlaced = false;
    for (const key of state.placementOrder) {
      const placement = state.placements.get(key);
      if (placement && (placement.category === 'special' || (placement.module && placement.module.category === 'special'))) {
        hasSpecialPlaced = true;
        break;
      }
    }
    if (dom.legendSpecial) {
      dom.legendSpecial.hidden = !hasSpecialPlaced;
    }

    let dictionary = [];
    const seenSigs = new Set();
    for (const mod of rawList) {
      const cat = mod.category || 'room';
      if (cat === 'corridor') continue;
      if (cat === 'special' && (counts.get(mod.id) || 0) === 0) continue;
      const area = (mod.area || 0).toFixed(1);
      const vCount = mod.poly ? mod.poly.length : 0;
      const sig = `${cat}_a${area}_v${vCount}`;
      if (!seenSigs.has(sig)) {
        seenSigs.add(sig);
        dictionary.push(mod);
      }
    }

    dom.dictionaryCount.textContent = `${dictionary.length} ${dictionary.length === 1 ? 'module' : 'modules'}`;

    if (!dictionary.length) {
      const empty = document.createElement('p');
      empty.className = 'empty-copy';
      empty.textContent = 'Waiting for the first generated site.';
      dom.dictionaryList.appendChild(empty);
      return;
    }

    for (const module of dictionary) {
      const category = CATEGORY_COLORS[module.category] ? module.category : 'room';
      const card = document.createElement('article');
      card.className = 'dictionary-card';
      card.setAttribute('role', 'listitem');

      // Hover highlights
      card.addEventListener('mouseenter', () => {
        state.hoveredModuleId = module.id;
        state.lastHoveredModuleId = module.id;
        state.lastFrameTime = performance.now();
        requestRender();
      });
      card.addEventListener('mouseleave', () => {
        state.hoveredModuleId = null;
        state.lastFrameTime = performance.now();
        requestRender();
      });

      const swatch = document.createElement('span');
      swatch.className = 'dictionary-swatch';
      swatch.style.background = 'none';
      swatch.style.border = 'none';
      swatch.innerHTML = createPolygonSVG(module.poly, category, 28);

      const copy = document.createElement('span');
      copy.className = 'dictionary-copy';
      const name = document.createElement('strong');
      name.textContent = module.name || String(module.id ?? 'Module');
      const detail = document.createElement('small');
      const area = finiteOr(module.area, Array.isArray(module.poly) ? polygonArea(normalizePolygon(module.poly)) : NaN);
      
      const freq = counts.get(module.id) || 0;
      detail.textContent = `${category}${Number.isFinite(area) ? ` · ${formatArea(area)}` : ''} · x${freq}`;
      
      copy.append(name, detail);
      card.append(swatch, copy);
      dom.dictionaryList.appendChild(card);
    }
  }

  function drawHistory() {
    const canvas = dom.historyCanvas;
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(1, Math.round(rect.width || 320));
    const height = Math.max(1, Math.round(rect.height || 88));
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const totalEpisodes = state.scoreHistory.length;
    const values = (state.showFullHistory || totalEpisodes <= 100) 
      ? state.scoreHistory 
      : state.scoreHistory.slice(-100);

    const isHovered = Boolean(state.historyHovered);

    if (dom.historyCanvas) {
      dom.historyCanvas.style.cursor = totalEpisodes > 100 ? 'pointer' : 'default';
    }

    if (dom.trendKicker && dom.trendTitle) {
      if (totalEpisodes <= 100) {
        dom.trendKicker.textContent = 'All episodes';
        dom.trendTitle.textContent = totalEpisodes > 0 
          ? `Score trend (Ep 1-${totalEpisodes})`
          : 'Score trend';
      } else if (state.showFullHistory) {
        dom.trendKicker.textContent = 'All episodes (click to crop)';
        dom.trendTitle.textContent = `Score trend (Ep 1-${totalEpisodes})`;
      } else {
        dom.trendKicker.textContent = 'Recent 100 episodes (click to expand)';
        const startEp = Math.max(1, totalEpisodes - 99);
        dom.trendTitle.textContent = `Score trend (Ep ${startEp}-${totalEpisodes})`;
      }
    }

    dom.trendValue.textContent = state.scoreHistory.length 
      ? formatDecimal(state.scoreHistory[state.scoreHistory.length - 1], 1) 
      : '—';

    const marginLeft = 38;
    const marginRight = 12;
    const marginTop = 12;
    const marginBottom = 16;
    const gridWidth = width - marginLeft - marginRight;
    const gridHeight = height - marginTop - marginBottom;

    ctx.strokeStyle = 'rgba(255,255,255,0.055)';
    ctx.lineWidth = 1;
    for (const ratio of [0.0, 0.25, 0.5, 0.75, 1.0]) {
      const y = Math.round(marginTop + gridHeight * ratio) + 0.5;
      ctx.beginPath();
      ctx.moveTo(marginLeft, y);
      ctx.lineTo(width - marginRight, y);
      ctx.stroke();
    }

    if (values.length < 2) {
      ctx.fillStyle = '#77837a';
      ctx.font = '9px ui-sans-serif, system-ui, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('Episode scores will appear here', width / 2, height / 2 + 3);
      return;
    }

    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = Math.max(8, max - min);

    ctx.fillStyle = '#adb9b0';
    ctx.font = '9px ui-sans-serif, system-ui, sans-serif';
    ctx.textAlign = 'right';

    ctx.fillText(formatDecimal(max, 1), marginLeft - 6, marginTop + 3);
    ctx.fillText(formatDecimal(min, 1), marginLeft - 6, height - marginBottom + 3);
    ctx.fillText(formatDecimal(min + span / 2, 1), marginLeft - 6, marginTop + gridHeight / 2 + 3);

    ctx.fillStyle = '#77837a';
    ctx.font = '9px ui-sans-serif, system-ui, sans-serif';

    const startEp = (state.showFullHistory || totalEpisodes <= 100) ? 1 : Math.max(1, totalEpisodes - 99);
    ctx.textAlign = 'left';
    ctx.fillText(`Ep ${startEp}`, marginLeft, height - 4);

    ctx.textAlign = 'right';
    ctx.fillText(`Ep ${totalEpisodes}`, width - marginRight, height - 4);

    const points = values.map((value, index) => ({
      x: marginLeft + (index / (values.length - 1)) * gridWidth,
      y: marginTop + gridHeight - ((value - min) / span) * gridHeight
    }));

    // Transition factor with smooth cubic ease
    const t = Math.max(0.0, Math.min(1.0, state.historyHoverFactor || 0.0));
    const ease = t * t * (3 - 2 * t);

    // Window Smoothing Function (Adaptive Gaussian-Weighted Moving Window)
    function computeWindowSmoothedPoints(rawValues, basePoints) {
      if (rawValues.length < 2) return basePoints;
      const n = rawValues.length;
      // Adaptive radius based on total points: k=1 for n<6, k=2 for n<15, up to k=8 for n>=60
      const k = Math.max(1, Math.min(8, Math.floor(n / 7)));
      const sigma = Math.max(0.8, k * 0.55);

      return basePoints.map((pt, i) => {
        let sumY = 0;
        let sumW = 0;
        const start = Math.max(0, i - k);
        const end = Math.min(n - 1, i + k);
        for (let j = start; j <= end; j++) {
          const dist = Math.abs(j - i);
          const w = Math.exp(-(dist * dist) / (2 * sigma * sigma));
          sumY += basePoints[j].y * w;
          sumW += w;
        }
        return { x: pt.x, y: sumY / sumW };
      });
    }

    // 1. Draw area fill gradient
    const topAlpha = 0.22 - 0.10 * ease; // from 0.22 down to 0.12 (soft gentle fade)
    const gradient = ctx.createLinearGradient(0, marginTop, 0, height - marginBottom);
    gradient.addColorStop(0, `rgba(196,219,139,${topAlpha.toFixed(3)})`);
    gradient.addColorStop(1, 'rgba(196,219,139,0)');
    ctx.beginPath();
    ctx.moveTo(points[0].x, height - marginBottom);
    for (const point of points) ctx.lineTo(point.x, point.y);
    ctx.lineTo(points[points.length - 1].x, height - marginBottom);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();

    // Helper to draw raw score line
    function drawScoreLine() {
      const scoreAlpha = 1.0 - 0.50 * ease; // from 1.0 down to 0.50 (clean moderate fade)
      const scoreWidth = 1.7 - 0.20 * ease; // from 1.7 down to 1.5
      ctx.beginPath();
      points.forEach((point, index) => {
        if (index === 0) ctx.moveTo(point.x, point.y);
        else ctx.lineTo(point.x, point.y);
      });
      ctx.strokeStyle = `rgba(196, 219, 139, ${scoreAlpha.toFixed(3)})`;
      ctx.lineWidth = scoreWidth;
      ctx.lineJoin = 'round';
      ctx.lineCap = 'round';
      ctx.stroke();
    }

    // Helper to draw smoothed trend line
    function drawSmoothedLine() {
      if (points.length < 2) return;
      const smoothed = computeWindowSmoothedPoints(values, points);
      const fitAlpha = 0.45 + 0.55 * ease; // from 0.45 up to 1.0 (crisp & solid)
      const fitWidth = 1.5 + 0.25 * ease; // from 1.5 up to 1.75

      ctx.beginPath();
      smoothed.forEach((point, index) => {
        if (index === 0) ctx.moveTo(point.x, point.y);
        else ctx.lineTo(point.x, point.y);
      });
      ctx.strokeStyle = `rgba(196, 219, 139, ${fitAlpha.toFixed(3)})`;
      ctx.lineWidth = fitWidth;
      ctx.lineJoin = 'round';
      ctx.lineCap = 'round';

      // Transition dash smoothly to solid
      if (ease >= 0.75) {
        ctx.setLineDash([]);
      } else {
        const dashLen = 4 * (1 - ease / 0.75);
        ctx.setLineDash([Math.max(0.1, dashLen), Math.max(0.1, dashLen)]);
      }
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // Layer ordering: when hovered (ease >= 0.5), smoothed line is drawn in the foreground on top
    if (ease >= 0.5) {
      drawScoreLine();
      drawSmoothedLine();
    } else {
      drawSmoothedLine();
      drawScoreLine();
    }
  }

  function setupCanvasEvents() {
    dom.canvas.addEventListener('pointerdown', (event) => {
      const point = canvasPoint(event);
      view.pointers.set(event.pointerId, point);
      dom.canvas.setPointerCapture(event.pointerId);
      dom.canvas.dataset.panning = 'true';
      beginPointerGesture();
    });

    dom.canvas.addEventListener('pointermove', (event) => {
      if (!view.pointers.has(event.pointerId)) return;
      view.pointers.set(event.pointerId, canvasPoint(event));
      updatePointerGesture();
    });

    const endPointer = (event) => {
      view.pointers.delete(event.pointerId);
      if (view.pointers.size === 0) {
        view.gesture = null;
        dom.canvas.dataset.panning = 'false';
      } else {
        beginPointerGesture();
      }
    };

    dom.canvas.addEventListener('pointerup', endPointer);
    dom.canvas.addEventListener('pointercancel', endPointer);

    dom.canvas.addEventListener('wheel', (event) => {
      event.preventDefault();
      const point = canvasPoint(event);
      const world = screenToWorld(point.x, point.y);
      const nextZoom = clamp(view.zoom * Math.exp(-event.deltaY * 0.0012), view.minZoom, view.maxZoom);
      view.zoom = nextZoom;
      view.panX = point.x - world.x * nextZoom;
      view.panY = point.y - world.y * nextZoom;
      view.userAdjusted = true;
      requestRender();
    }, { passive: false });

    dom.canvas.addEventListener('keydown', (event) => {
      const panStep = event.shiftKey ? 60 : 24;
      let handled = true;
      if (event.key === 'ArrowLeft') view.panX += panStep;
      else if (event.key === 'ArrowRight') view.panX -= panStep;
      else if (event.key === 'ArrowUp') view.panY += panStep;
      else if (event.key === 'ArrowDown') view.panY -= panStep;
      else if (event.key === '+' || event.key === '=') zoomAt(view.width / 2, view.height / 2, 1.18);
      else if (event.key === '-' || event.key === '_') zoomAt(view.width / 2, view.height / 2, 1 / 1.18);
      else if (event.key === '0') fitAllSites();
      else handled = false;
      if (handled) {
        event.preventDefault();
        view.userAdjusted = true;
        requestRender();
      }
    });
  }

  function canvasPoint(event) {
    const rect = dom.canvas.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  function beginPointerGesture() {
    const points = [...view.pointers.values()];
    if (points.length >= 2) {
      const midpoint = midpointOf(points[0], points[1]);
      view.gesture = {
        kind: 'pinch',
        startDistance: Math.max(1, pointDistance(points[0], points[1])),
        startZoom: view.zoom,
        worldAnchor: screenToWorld(midpoint.x, midpoint.y)
      };
    } else if (points.length === 1) {
      view.gesture = {
        kind: 'pan',
        startPoint: points[0],
        startPanX: view.panX,
        startPanY: view.panY
      };
    }
  }

  function updatePointerGesture() {
    if (!view.gesture) return;
    const points = [...view.pointers.values()];
    if (view.gesture.kind === 'pan' && points.length === 1) {
      view.panX = view.gesture.startPanX + points[0].x - view.gesture.startPoint.x;
      view.panY = view.gesture.startPanY + points[0].y - view.gesture.startPoint.y;
    } else if (view.gesture.kind === 'pinch' && points.length >= 2) {
      const midpoint = midpointOf(points[0], points[1]);
      const ratio = pointDistance(points[0], points[1]) / view.gesture.startDistance;
      view.zoom = clamp(view.gesture.startZoom * ratio, view.minZoom, view.maxZoom);
      view.panX = midpoint.x - view.gesture.worldAnchor.x * view.zoom;
      view.panY = midpoint.y - view.gesture.worldAnchor.y * view.zoom;
    } else {
      beginPointerGesture();
    }
    view.userAdjusted = true;
    requestRender();
  }

  function zoomAt(screenX, screenY, multiplier) {
    const world = screenToWorld(screenX, screenY);
    view.zoom = clamp(view.zoom * multiplier, view.minZoom, view.maxZoom);
    view.panX = screenX - world.x * view.zoom;
    view.panY = screenY - world.y * view.zoom;
  }

  function setupResizeHandling() {
    if ('ResizeObserver' in window) {
      const observer = new ResizeObserver(() => {
        const shouldRefit = state.hasSite && !view.userAdjusted;
        resizeCanvas();
        if (shouldRefit) fitAllSites();
        drawHistory();
        state.debugScoreSignature = null;
        drawDebugScoreHistory();
      });
      observer.observe(dom.stage);
      observer.observe(dom.historyCanvas);
      if (dom.debugScoreCanvas) observer.observe(dom.debugScoreCanvas);
    } else {
      window.addEventListener('resize', () => {
        resizeCanvas();
        if (state.hasSite && !view.userAdjusted) fitAllSites();
        drawHistory();
        state.debugScoreSignature = null;
        drawDebugScoreHistory();
      });
    }
  }

  function resizeCanvas() {
    const rect = dom.canvas.getBoundingClientRect();
    const width = Math.max(1, Math.round(rect.width));
    const height = Math.max(1, Math.round(rect.height));
    const dpr = Math.min(window.devicePixelRatio || 1, 2.5);
    if (width === view.width && height === view.height && dpr === view.dpr) return;
    view.width = width;
    view.height = height;
    view.dpr = dpr;
    dom.canvas.width = Math.round(width * dpr);
    dom.canvas.height = Math.round(height * dpr);
    requestRender();
  }

  function fitAllSites() {
    if (!state.boundaries.length || view.width <= 1 || view.height <= 1) return;
    let bounds = null;
    for (const boundary of state.boundaries) bounds = unionBounds(bounds, boundary.bounds);
    if (!bounds) return;

    const worldWidth = Math.max(1, bounds.maxX - bounds.minX);
    const worldHeight = Math.max(1, bounds.maxY - bounds.minY + 4);
    const horizontalPadding = view.width < 600 ? 34 : 70;
    const topPadding = view.width < 760 ? 180 : 122;
    const bottomPadding = 74;
    const usableWidth = Math.max(80, view.width - horizontalPadding * 2);
    const usableHeight = Math.max(80, view.height - topPadding - bottomPadding);
    view.zoom = clamp(Math.min(usableWidth / worldWidth, usableHeight / worldHeight), view.minZoom, 30);
    view.panX = horizontalPadding + (usableWidth - worldWidth * view.zoom) / 2 - bounds.minX * view.zoom;
    view.panY = topPadding + (usableHeight - worldHeight * view.zoom) / 2 - bounds.minY * view.zoom;
    view.userAdjusted = false;
    requestRender();
  }

  function requestRender() {
    if (view.renderFrame !== null) return;
    view.renderFrame = window.requestAnimationFrame(renderCanvas);
  }

  function renderCanvas() {
    view.renderFrame = null;
    
    // Smooth 1s transition animation for dimming highlight
    const now = performance.now();
    const dt = state.lastFrameTime ? (now - state.lastFrameTime) / 1000.0 : 0.016;
    state.lastFrameTime = now;
    
    const targetDim = state.hoveredModuleId !== null ? 1.0 : 0.0;
    const diff = targetDim - state.dimmingFactor;
    if (Math.abs(diff) > 1e-4) {
      const step = dt * Math.sign(diff); // 1-second rate
      if (Math.abs(step) >= Math.abs(diff)) {
        state.dimmingFactor = targetDim;
        if (targetDim === 0.0) {
          state.lastHoveredModuleId = null;
        }
      } else {
        state.dimmingFactor += step;
      }
      requestRender();
    }
    const ctx = context;
    ctx.setTransform(view.dpr, 0, 0, view.dpr, 0, 0);
    ctx.clearRect(0, 0, view.width, view.height);
    ctx.fillStyle = '#e9e6de';
    ctx.fillRect(0, 0, view.width, view.height);

    drawGrid(ctx);
    if (state.showSDFGrid) drawSDFGrid(ctx);
    drawSites(ctx);
    drawPlacements(ctx);
    drawGraph(ctx);
    if (shouldDrawWallCache()) drawWallCache(ctx);
    drawSiteLabels(ctx);
    drawScaleBar(ctx);
    if (state.wallComputing) drawWallProgress(ctx);
  }

  function drawSDFGrid(ctx) {
    if (!state.boundaries || !state.boundaries.length) return;

    for (const boundary of state.boundaries) {
      const outer = boundary.outer;
      const holes = boundary.holes || [];
      if (!outer || outer.length < 3) continue;

      let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
      for (const pt of outer) {
        if (pt.x < minX) minX = pt.x;
        if (pt.x > maxX) maxX = pt.x;
        if (pt.y < minY) minY = pt.y;
        if (pt.y > maxY) maxY = pt.y;
      }

      const margin = 8;
      minX -= margin; maxX += margin;
      minY -= margin; maxY += margin;

      const gridStep = 1.5;

      function pointToSegmentDist(pt, p1, p2) {
        const dx = p2.x - p1.x;
        const dy = p2.y - p1.y;
        const l2 = dx * dx + dy * dy;
        if (l2 === 0) return Math.hypot(pt.x - p1.x, pt.y - p1.y);
        let t = ((pt.x - p1.x) * dx + (pt.y - p1.y) * dy) / l2;
        t = Math.max(0, Math.min(1, t));
        return Math.hypot(pt.x - (p1.x + t * dx), pt.y - (p1.y + t * dy));
      }

      function pointToPolyDist(pt, poly) {
        if (!poly || poly.length < 2) return Infinity;
        let minD = Infinity;
        for (let i = 0; i < poly.length; i++) {
          const p1 = poly[i];
          const p2 = poly[(i + 1) % poly.length];
          const d = pointToSegmentDist(pt, p1, p2);
          if (d < minD) minD = d;
        }
        return minD;
      }

      function isInsidePoly(pt, poly) {
        let inside = false;
        for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
          const xi = poly[i].x, yi = poly[i].y;
          const xj = poly[j].x, yj = poly[j].y;
          const intersect = ((yi > pt.y) !== (yj > pt.y)) && (pt.x < (xj - xi) * (pt.y - yi) / (yj - yi) + xi);
          if (intersect) inside = !inside;
        }
        return inside;
      }

      for (let x = minX; x <= maxX; x += gridStep) {
        for (let y = minY; y <= maxY; y += gridStep) {
          const pt = { x, y };
          const inOuter = isInsidePoly(pt, outer);
          const inHole = holes.some(h => isInsidePoly(pt, h));
          const isInsideSite = inOuter && !inHole;

          let dist = pointToPolyDist(pt, outer);
          for (const h of holes) {
            const hd = pointToPolyDist(pt, h);
            if (hd < dist) dist = hd;
          }

          const signedDist = isInsideSite ? dist : -dist;

          const sx = worldToScreenX(x);
          const sy = worldToScreenY(y);

          if (sx < -20 || sx > view.width + 20 || sy < -20 || sy > view.height + 20) continue;

          ctx.beginPath();
          const r = Math.min(5, Math.max(2, view.zoom * 0.35));
          ctx.arc(sx, sy, r, 0, Math.PI * 2);

          if (signedDist >= 0) {
            const alpha = Math.min(0.85, 0.25 + signedDist * 0.04);
            ctx.fillStyle = `rgba(0, 180, 160, ${alpha})`;
          } else {
            const alpha = Math.min(0.85, 0.25 + Math.abs(signedDist) * 0.04);
            ctx.fillStyle = `rgba(235, 75, 75, ${alpha})`;
          }
          ctx.fill();

          if (view.zoom >= 4.5) {
            ctx.font = '9px Inter, system-ui, sans-serif';
            ctx.fillStyle = signedDist >= 0 ? 'rgba(0, 80, 70, 0.9)' : 'rgba(160, 30, 30, 0.9)';
            ctx.textAlign = 'center';
            ctx.fillText(`${signedDist >= 0 ? '+' : ''}${signedDist.toFixed(1)}m`, sx, sy + r + 8);
          }
        }
      }
    }
  }

  function drawGrid(ctx) {
    const topLeft = screenToWorld(0, 0);
    const bottomRight = screenToWorld(view.width, view.height);
    let minorStep = 1;
    if (view.zoom < 4) minorStep = 5;
    else if (view.zoom < 8) minorStep = 2;
    const majorStep = minorStep * 5;

    drawGridSet(ctx, topLeft, bottomRight, minorStep, 'rgba(28, 37, 30, 0.055)', 0.7);
    drawGridSet(ctx, topLeft, bottomRight, majorStep, 'rgba(28, 37, 30, 0.105)', 0.9);
  }

  function drawGridSet(ctx, topLeft, bottomRight, step, color, lineWidth) {
    const minX = Math.floor(Math.min(topLeft.x, bottomRight.x) / step) * step;
    const maxX = Math.ceil(Math.max(topLeft.x, bottomRight.x) / step) * step;
    const minY = Math.floor(Math.min(topLeft.y, bottomRight.y) / step) * step;
    const maxY = Math.ceil(Math.max(topLeft.y, bottomRight.y) / step) * step;
    ctx.beginPath();
    for (let x = minX; x <= maxX; x += step) {
      const sx = worldToScreenX(x);
      ctx.moveTo(Math.round(sx) + 0.5, 0);
      ctx.lineTo(Math.round(sx) + 0.5, view.height);
    }
    for (let y = minY; y <= maxY; y += step) {
      const sy = worldToScreenY(y);
      ctx.moveTo(0, Math.round(sy) + 0.5);
      ctx.lineTo(view.width, Math.round(sy) + 0.5);
    }
    ctx.strokeStyle = color;
    ctx.lineWidth = lineWidth;
    ctx.stroke();
  }

  function drawSites(ctx) {
    for (const boundary of state.boundaries) {
      const path = new Path2D();
      appendPolygonPath(path, boundary.outer);
      for (const hole of boundary.holes) appendPolygonPath(path, hole);
      ctx.fillStyle = '#f8f6ef';
      ctx.fill(path, 'evenodd');

      ctx.strokeStyle = '#111712';
      ctx.lineWidth = 2.5;
      ctx.lineJoin = 'round';
      strokePolygon(ctx, boundary.outer);
      for (const hole of boundary.holes) strokePolygon(ctx, hole);
    }
  }

  function appendPolygonPath(path, polygon) {
    if (!polygon.length) return;
    path.moveTo(worldToScreenX(polygon[0].x), worldToScreenY(polygon[0].y));
    for (let index = 1; index < polygon.length; index += 1) {
      path.lineTo(worldToScreenX(polygon[index].x), worldToScreenY(polygon[index].y));
    }
    path.closePath();
  }

  function createWorldPolygonPath(polygon) {
    const path = new Path2D();
    if (!polygon.length) return path;
    path.moveTo(polygon[0].x, polygon[0].y);
    for (let index = 1; index < polygon.length; index += 1) {
      path.lineTo(polygon[index].x, polygon[index].y);
    }
    path.closePath();
    return path;
  }

  function strokePolygon(ctx, polygon) {
    if (polygon.length < 2) return;
    ctx.beginPath();
    ctx.moveTo(worldToScreenX(polygon[0].x), worldToScreenY(polygon[0].y));
    for (let index = 1; index < polygon.length; index += 1) {
      ctx.lineTo(worldToScreenX(polygon[index].x), worldToScreenY(polygon[index].y));
    }
    ctx.closePath();
    ctx.stroke();
  }

  function isPlacementMatchingHover(placement) {
    const hoverId = state.hoveredModuleId !== null ? state.hoveredModuleId : state.lastHoveredModuleId;
    if (hoverId === null) return true;
    if (placement.module.id === hoverId) return true;
    if (placement.components) {
      for (const comp of placement.components) {
        const compTypeId = (comp.module && comp.module.id) || comp.category;
        if (compTypeId === hoverId) return true;
      }
    }
    return false;
  }

  function isComponentMatchingHover(comp) {
    const hoverId = state.hoveredModuleId !== null ? state.hoveredModuleId : state.lastHoveredModuleId;
    if (hoverId === null) return true;
    const compTypeId = (comp.module && comp.module.id) || comp.category;
    return compTypeId === hoverId;
  }

  function drawPlacements(ctx) {
    const viewport = viewportWorldBounds(4);
    const visiblePlacements = [];
    ctx.save();
    ctx.transform(view.zoom, 0, 0, view.zoom, view.panX, view.panY);
    for (const key of state.placementOrder) {
      const placement = state.placements.get(key);
      if (!placement || !boundsIntersect(placement.bounds, viewport)) continue;
      visiblePlacements.push(placement);
      
      const dim = state.dimmingFactor;
      if (!state.disableMerging) {
        const match = isPlacementMatchingHover(placement);
        const opacity = match ? 1.0 : (1.0 - dim * 0.76);
        ctx.save();
        ctx.globalAlpha = opacity;
        if (placement.components) {
          for (const comp of placement.components) {
            ctx.fillStyle = CATEGORY_COLORS[comp.category] || CATEGORY_COLORS.room;
            ctx.fill(comp.worldPath);
          }
        } else {
          ctx.fillStyle = CATEGORY_COLORS[placement.module.category] || CATEGORY_COLORS.room;
          ctx.fill(placement.worldPath);
        }
        ctx.restore();
      } else {
        // Merging is disabled, draw each component separately with individual opacity checks
        if (placement.components) {
          for (const comp of placement.components) {
            const match = isComponentMatchingHover(comp);
            const opacity = match ? 1.0 : (1.0 - dim * 0.76);
            ctx.save();
            ctx.globalAlpha = opacity;
            ctx.fillStyle = CATEGORY_COLORS[comp.category] || CATEGORY_COLORS.room;
            ctx.fill(comp.worldPath);
            ctx.restore();
          }
        } else {
          const match = isPlacementMatchingHover(placement);
          const opacity = match ? 1.0 : (1.0 - dim * 0.76);
          ctx.save();
          ctx.globalAlpha = opacity;
          ctx.fillStyle = CATEGORY_COLORS[placement.module.category] || CATEGORY_COLORS.room;
          ctx.fill(placement.worldPath);
          ctx.restore();
        }
      }
    }
    ctx.restore();

    for (const placement of visiblePlacements) {
      const dim = state.dimmingFactor;
      if (state.disableMerging && placement.components) {
        for (const comp of placement.components) {
          const match = isComponentMatchingHover(comp);
          const opacity = match ? 1.0 : (1.0 - dim * 0.76);
          if (view.zoom >= 9 && comp.area * view.zoom * view.zoom >= 520) {
            ctx.save();
            ctx.globalAlpha = opacity;
            ctx.fillStyle = 'rgba(17,23,18,0.72)';
            ctx.font = `700 ${clamp(view.zoom * 0.48, 7, 11)}px ui-sans-serif, system-ui, sans-serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(String(comp.module ? comp.module.id : comp.id), worldToScreenX(comp.center.x), worldToScreenY(comp.center.y));
            ctx.restore();
          }
        }
      } else {
        const match = isPlacementMatchingHover(placement);
        const opacity = match ? 1.0 : (1.0 - dim * 0.76);
        if (view.zoom >= 9 && placement.area * view.zoom * view.zoom >= 520) {
          ctx.save();
          ctx.globalAlpha = opacity;
          ctx.fillStyle = 'rgba(17,23,18,0.72)';
          ctx.font = `700 ${clamp(view.zoom * 0.48, 7, 11)}px ui-sans-serif, system-ui, sans-serif`;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(String(placement.module.id), worldToScreenX(placement.center.x), worldToScreenY(placement.center.y));
          ctx.restore();
        }
      }
    }
  }

  function drawGraph(ctx) {
    const viewport = viewportWorldBounds(8);
    ctx.save();
    ctx.strokeStyle = 'rgba(25, 45, 32, 0.43)';
    ctx.lineWidth = 1.15;
    ctx.setLineDash([3, 4]);
    ctx.beginPath();
    for (const edge of state.graphEdges.values()) {
      const a = state.placements.get(edge.a);
      const b = state.placements.get(edge.b);
      if (!a || !b) continue;
      const edgeBounds = {
        minX: Math.min(a.center.x, b.center.x),
        minY: Math.min(a.center.y, b.center.y),
        maxX: Math.max(a.center.x, b.center.x),
        maxY: Math.max(a.center.y, b.center.y)
      };
      if (!boundsIntersect(edgeBounds, viewport)) continue;
      ctx.moveTo(worldToScreenX(a.center.x), worldToScreenY(a.center.y));
      ctx.lineTo(worldToScreenX(b.center.x), worldToScreenY(b.center.y));
    }
    ctx.stroke();
    ctx.setLineDash([]);

    for (const placement of state.placements.values()) {
      if (!pointInsideBounds(placement.center, viewport)) continue;
      const x = worldToScreenX(placement.center.x);
      const y = worldToScreenY(placement.center.y);
      ctx.beginPath();
      ctx.arc(x, y, placement.module.category === 'core' ? 3.2 : 2.35, 0, Math.PI * 2);
      ctx.fillStyle = placement.module.category === 'core' ? '#9f3e2e' : '#284b35';
      ctx.fill();
      ctx.strokeStyle = 'rgba(248,246,239,0.9)';
      ctx.lineWidth = 0.8;
      ctx.stroke();
    }
    ctx.restore();
  }

  function shouldDrawWallCache() {
    const cache = state.wallCache;
    return Boolean(
      cache &&
      cache.revision === state.placementRevision &&
      sameToken(cache.generationId, state.generationId) &&
      sameToken(cache.episode, state.episode) &&
      (state.phase === 'paused' || state.phase === 'complete')
    );
  }

  function drawWallCache(ctx) {
    ctx.save();
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    ctx.beginPath();
    for (const fragment of state.wallCache.shared) drawFragmentPath(ctx, fragment);
    ctx.strokeStyle = 'rgba(55, 65, 57, 0.72)';
    ctx.lineWidth = 1.05;
    ctx.stroke();

    ctx.beginPath();
    for (const fragment of state.wallCache.exposed) drawFragmentPath(ctx, fragment);
    ctx.strokeStyle = '#111712';
    ctx.lineWidth = 3.1;
    ctx.stroke();
    ctx.restore();
  }

  function drawFragmentPath(ctx, fragment) {
    ctx.moveTo(worldToScreenX(fragment.a.x), worldToScreenY(fragment.a.y));
    ctx.lineTo(worldToScreenX(fragment.b.x), worldToScreenY(fragment.b.y));
  }

  function drawSiteLabels(ctx) {
    ctx.save();
    ctx.font = '700 9px ui-sans-serif, system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    for (const boundary of state.boundaries) {
      const area = state.areasByInstance.get(String(boundary.instanceIdx)) || { filled: 0 };
      const label = `FLOOR ${String(Number(boundary.instanceIdx) + 1).padStart(2, '0')}  ·  SITE ${Math.round(boundary.siteArea)} m²  ·  FILLED ${Math.round(area.filled)} m²`;
      const x = worldToScreenX((boundary.bounds.minX + boundary.bounds.maxX) / 2);
      const y = worldToScreenY(boundary.bounds.maxY) + 17;
      const width = ctx.measureText(label).width + 18;
      roundedRectPath(ctx, x - width / 2, y - 10, width, 20, 7);
      ctx.fillStyle = 'rgba(248,246,239,0.9)';
      ctx.fill();
      ctx.strokeStyle = 'rgba(17,23,18,0.12)';
      ctx.lineWidth = 0.8;
      ctx.stroke();
      ctx.fillStyle = '#48534b';
      ctx.fillText(label, x, y + 0.5);
    }
    ctx.restore();
  }

  function drawScaleBar(ctx) {
    const targetWidth = clamp(view.width * 0.15, 108, 176);
    const rawD = targetWidth / (10 * view.zoom);
    const distance = niceDistance(rawD);
    const offsets = [0, 1, 2, 5, 10].map((factor) => factor * distance * view.zoom);
    const x = Math.max(18, view.width - offsets[4] - 22);
    const y = view.height - 95;

    const y_top = y - 6;
    const y_bottom = y;

    ctx.save();
    ctx.strokeStyle = '#111712';
    ctx.fillStyle = '#111712';
    ctx.lineWidth = 1.15;
    ctx.lineCap = 'butt';
    ctx.lineJoin = 'miter';
    ctx.font = '700 8.5px ui-sans-serif, system-ui, -apple-system, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'bottom';

    // 1. Draw the crenellated scale bar line
    ctx.beginPath();
    ctx.moveTo(x + offsets[0], y_bottom);
    ctx.lineTo(x + offsets[0], y_top);

    for (let i = 0; i < offsets.length - 1; i++) {
      const y_level = (i % 2 === 0) ? y_top : y_bottom;
      if (i > 0) {
        const y_prev_level = ((i - 1) % 2 === 0) ? y_top : y_bottom;
        ctx.lineTo(x + offsets[i], y_prev_level);
        ctx.lineTo(x + offsets[i], y_level);
      }
      ctx.lineTo(x + offsets[i + 1], y_level);
    }

    // Last vertical tick down/up to opposite level
    const last_segment_idx = offsets.length - 2;
    const y_last_level = (last_segment_idx % 2 === 0) ? y_top : y_bottom;
    const y_opposite_level = (y_last_level === y_top) ? y_bottom : y_top;
    ctx.lineTo(x + offsets[offsets.length - 1], y_opposite_level);
    ctx.stroke();

    // 2. Draw labels above the scale bar
    offsets.forEach((offset, index) => {
      const factor = [0, 1, 2, 5, 10][index];
      const val = formatDistance(factor * distance);
      const isLast = index === offsets.length - 1;
      
      // Draw label text
      ctx.fillText(isLast ? `${val}m` : val, x + offset, y_top - 4);
    });

    ctx.restore();
  }

  function drawWallProgress(ctx) {
    const label = 'RESOLVING VECTOR WALLS';
    ctx.save();
    ctx.font = '700 8px ui-monospace, SFMono-Regular, monospace';
    const width = ctx.measureText(label).width + 18;
    roundedRectPath(ctx, view.width - width - 19, view.height - 130, width, 22, 7);
    ctx.fillStyle = 'rgba(18,24,19,0.86)';
    ctx.fill();
    ctx.fillStyle = '#c4db8b';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(label, view.width - width / 2 - 19, view.height - 119);
    ctx.restore();
  }

  function scheduleWallCache(onComplete) {
    const existing = state.wallCache;
    if (
      existing &&
      existing.revision === state.placementRevision &&
      sameToken(existing.generationId, state.generationId) &&
      sameToken(existing.episode, state.episode)
    ) {
      if (typeof onComplete === 'function') onComplete();
      requestRender();
      return;
    }

    cancelWallJob();
    const token = state.wallJobToken;
    const revision = state.placementRevision;
    const generationId = state.generationId;
    const episode = state.episode;
    const snapshot = [];
    for (const key of state.placementOrder) {
      const placement = state.placements.get(key);
      if (!placement) continue;
      if (state.disableMerging && placement.components) {
        for (const comp of placement.components) {
          snapshot.push({
            key: placement.key + '-' + comp.id,
            instanceIdx: placement.instanceIdx,
            poly: comp.poly.map((point) => ({ x: point.x, y: point.y }))
          });
        }
      } else {
        snapshot.push({
          key: placement.key,
          instanceIdx: placement.instanceIdx,
          poly: placement.poly.map((point) => ({ x: point.x, y: point.y }))
        });
      }
    }

    state.wallComputing = snapshot.length > 0;
    requestRender();

    const launch = () => {
      state.wallSchedule = null;
      if (!isWallJobCurrent(token, revision, generationId, episode)) return;
      launchWallWorker(snapshot, token, revision, generationId, episode, onComplete);
    };

    if (!snapshot.length) {
      acceptWallFragments({ exposed: [], shared: [] }, token, revision, generationId, episode, onComplete);
    } else if ('requestIdleCallback' in window) {
      state.wallSchedule = {
        kind: 'idle',
        id: window.requestIdleCallback(launch, { timeout: 220 })
      };
    } else {
      state.wallSchedule = {
        kind: 'timeout',
        id: window.setTimeout(launch, 0)
      };
    }
  }

  function cancelWallJob() {
    state.wallJobToken += 1;
    if (state.wallSchedule) {
      if (state.wallSchedule.kind === 'idle' && typeof window.cancelIdleCallback === 'function') {
        window.cancelIdleCallback(state.wallSchedule.id);
      } else {
        window.clearTimeout(state.wallSchedule.id);
      }
      state.wallSchedule = null;
    }
    if (state.wallWorker) {
      state.wallWorker.terminate();
      state.wallWorker = null;
    }
    state.wallComputing = false;
  }

  function isWallJobCurrent(token, revision, generationId, episode) {
    return Boolean(
      token === state.wallJobToken &&
      revision === state.placementRevision &&
      sameToken(generationId, state.generationId) &&
      sameToken(episode, state.episode) &&
      (state.phase === 'paused' || state.phase === 'complete')
    );
  }

  function launchWallWorker(snapshot, token, revision, generationId, episode, onComplete) {
    if (!isWallJobCurrent(token, revision, generationId, episode)) return;

    let worker;
    try {
      worker = createWallWorker();
    } catch (error) {
      finishWallJobWithError(error, token, revision, generationId, episode, onComplete);
      return;
    }

    if (!worker) {
      try {
        const fragments = computeExactWallFragments(snapshot);
        acceptWallFragments(fragments, token, revision, generationId, episode, onComplete);
      } catch (error) {
        finishWallJobWithError(error, token, revision, generationId, episode, onComplete);
      }
      return;
    }

    state.wallWorker = worker;
    let settled = false;
    const releaseWorker = () => {
      if (settled) return false;
      settled = true;
      if (state.wallWorker === worker) state.wallWorker = null;
      worker.terminate();
      return true;
    };

    worker.addEventListener('message', (event) => {
      if (!releaseWorker()) return;
      const payload = event.data || {};
      if (payload.type === 'wallError') {
        finishWallJobWithError(new Error(payload.message || 'Vector wall worker failed.'), token, revision, generationId, episode, onComplete);
        return;
      }
      if (payload.type !== 'wallFragments' || payload.token !== token) return;
      acceptWallFragments(payload.fragments, token, revision, generationId, episode, onComplete);
    });

    worker.addEventListener('error', (event) => {
      if (!releaseWorker()) return;
      event.preventDefault();
      finishWallJobWithError(new Error(event.message || 'Vector wall worker failed.'), token, revision, generationId, episode, onComplete);
    });

    worker.postMessage({ token, placements: snapshot });
  }

  function createWallWorker() {
    if (
      typeof window.Worker !== 'function' ||
      typeof window.Blob !== 'function' ||
      !window.URL ||
      typeof window.URL.createObjectURL !== 'function'
    ) return null;

    const workerSource = [
      "'use strict';",
      clamp.toString(),
      edgeOverlapInterval.toString(),
      mergeIntervals.toString(),
      fragmentOnEdge.toString(),
      fragmentIdentity.toString(),
      computeExactWallFragments.toString(),
      'self.onmessage = function (event) {',
      '  const payload = event.data || {};',
      '  try {',
      '    const placements = Array.isArray(payload.placements) ? payload.placements : [];',
      '    const fragments = computeExactWallFragments(placements);',
      "    self.postMessage({ type: 'wallFragments', token: payload.token, fragments: fragments });",
      '  } catch (error) {',
      "    self.postMessage({ type: 'wallError', token: payload.token, message: error && error.message ? error.message : String(error) });",
      '  }',
      '};'
    ].join('\n');
    const objectUrl = window.URL.createObjectURL(new Blob([workerSource], { type: 'text/javascript' }));
    try {
      return new Worker(objectUrl);
    } finally {
      window.URL.revokeObjectURL(objectUrl);
    }
  }

  function acceptWallFragments(fragments, token, revision, generationId, episode, onComplete) {
    if (!isWallJobCurrent(token, revision, generationId, episode)) return;
    const exposed = fragments && Array.isArray(fragments.exposed) ? fragments.exposed : [];
    const shared = fragments && Array.isArray(fragments.shared) ? fragments.shared : [];
    state.wallCache = { generationId, episode, revision, exposed, shared };
    state.wallComputing = false;
    requestRender();
    if (typeof onComplete === 'function') onComplete();
  }

  function finishWallJobWithError(error, token, revision, generationId, episode, onComplete) {
    if (!isWallJobCurrent(token, revision, generationId, episode)) return;
    state.wallComputing = false;
    requestRender();
    showToast(error && error.message ? error.message : 'Vector wall outline could not be resolved.', 'error');
    if (typeof onComplete === 'function') onComplete();
  }

  function computeExactWallFragments(placements) {
    const edges = [];
    for (const placement of placements) {
      for (let index = 0; index < placement.poly.length; index += 1) {
        const a = placement.poly[index];
        const b = placement.poly[(index + 1) % placement.poly.length];
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const length = Math.hypot(dx, dy);
        if (length < 1e-6) continue;
        edges.push({
          a,
          b,
          dx,
          dy,
          length,
          ux: dx / length,
          uy: dy / length,
          placementKey: placement.key,
          instanceIdx: String(placement.instanceIdx),
          bounds: {
            minX: Math.min(a.x, b.x),
            minY: Math.min(a.y, b.y),
            maxX: Math.max(a.x, b.x),
            maxY: Math.max(a.y, b.y)
          }
        });
      }
    }

    const cellSize = 10;
    const spatialIndex = new Map();
    edges.forEach((edge, edgeIndex) => {
      const minCellX = Math.floor((edge.bounds.minX - 0.01) / cellSize);
      const maxCellX = Math.floor((edge.bounds.maxX + 0.01) / cellSize);
      const minCellY = Math.floor((edge.bounds.minY - 0.01) / cellSize);
      const maxCellY = Math.floor((edge.bounds.maxY + 0.01) / cellSize);
      for (let x = minCellX; x <= maxCellX; x += 1) {
        for (let y = minCellY; y <= maxCellY; y += 1) {
          const key = `${edge.instanceIdx}:${x}:${y}`;
          const bucket = spatialIndex.get(key) || [];
          bucket.push(edgeIndex);
          spatialIndex.set(key, bucket);
        }
      }
    });

    const exposed = [];
    const sharedMap = new Map();

    edges.forEach((edge, edgeIndex) => {
      const candidateIndexes = new Set();
      const minCellX = Math.floor((edge.bounds.minX - 0.01) / cellSize);
      const maxCellX = Math.floor((edge.bounds.maxX + 0.01) / cellSize);
      const minCellY = Math.floor((edge.bounds.minY - 0.01) / cellSize);
      const maxCellY = Math.floor((edge.bounds.maxY + 0.01) / cellSize);
      for (let x = minCellX; x <= maxCellX; x += 1) {
        for (let y = minCellY; y <= maxCellY; y += 1) {
          const bucket = spatialIndex.get(`${edge.instanceIdx}:${x}:${y}`) || [];
          for (const candidateIndex of bucket) candidateIndexes.add(candidateIndex);
        }
      }

      const intervals = [];
      for (const candidateIndex of candidateIndexes) {
        if (candidateIndex === edgeIndex) continue;
        const candidate = edges[candidateIndex];
        if (candidate.placementKey === edge.placementKey) continue;
        const interval = edgeOverlapInterval(edge, candidate);
        if (interval) intervals.push(interval);
      }

      const merged = mergeIntervals(intervals, edge.length);
      let cursor = 0;
      for (const interval of merged) {
        if (interval.start - cursor > 0.001) exposed.push(fragmentOnEdge(edge, cursor, interval.start));
        const shared = fragmentOnEdge(edge, interval.start, interval.end);
        sharedMap.set(fragmentIdentity(shared), shared);
        cursor = Math.max(cursor, interval.end);
      }
      if (edge.length - cursor > 0.001) exposed.push(fragmentOnEdge(edge, cursor, edge.length));
    });

    // Reclassify narrow opposing slit/notch fragments (< 0.06m, <= 1 deg) as interior shared walls
    const filteredExposed = [];
    const skipIndices = new Set();
    const cosThreshold = Math.cos(1.0 * Math.PI / 180.0);
    for (let i = 0; i < exposed.length; i += 1) {
      if (skipIndices.has(i)) continue;
      const s1 = exposed[i];
      const dx1 = s1.b.x - s1.a.x;
      const dy1 = s1.b.y - s1.a.y;
      const l1 = Math.hypot(dx1, dy1);
      if (l1 <= 1e-5) continue;
      const u1x = dx1 / l1;
      const u1y = dy1 / l1;

      let isSlit = false;
      for (let j = i + 1; j < exposed.length; j += 1) {
        if (skipIndices.has(j)) continue;
        const s2 = exposed[j];
        const dx2 = s2.b.x - s2.a.x;
        const dy2 = s2.b.y - s2.a.y;
        const l2 = Math.hypot(dx2, dy2);
        if (l2 <= 1e-5) continue;
        const u2x = dx2 / l2;
        const u2y = dy2 / l2;

        const dot = u1x * u2x + u1y * u2y;
        if (dot <= -cosThreshold) {
          const distA = Math.abs((s2.a.x - s1.a.x) * u1y - (s2.a.y - s1.a.y) * u1x);
          const distB = Math.abs((s2.b.x - s1.a.x) * u1y - (s2.b.y - s1.a.y) * u1x);
          if (distA < 0.06 && distB < 0.06) {
            const projA = (s2.a.x - s1.a.x) * u1x + (s2.a.y - s1.a.y) * u1y;
            const projB = (s2.b.x - s1.a.x) * u1x + (s2.b.y - s1.a.y) * u1y;
            const minProj = Math.min(projA, projB);
            const maxProj = Math.max(projA, projB);
            const overlapLen = Math.min(l1, maxProj) - Math.max(0, minProj);
            if (overlapLen > 0.05) {
              skipIndices.add(i);
              skipIndices.add(j);
              sharedMap.set(fragmentIdentity(s1), s1);
              sharedMap.set(fragmentIdentity(s2), s2);
              isSlit = true;
              break;
            }
          }
        }
      }
      if (!isSlit) filteredExposed.push(s1);
    }

    return { exposed: filteredExposed, shared: [...sharedMap.values()] };
  }

  function edgeOverlapInterval(edge, candidate) {
    const directionCross = edge.ux * candidate.uy - edge.uy * candidate.ux;
    if (Math.abs(directionCross) > 0.001) return null;
    const lineDistance = Math.abs((candidate.a.x - edge.a.x) * edge.uy - (candidate.a.y - edge.a.y) * edge.ux);
    if (lineDistance > 0.003) return null;

    const startProjection = (candidate.a.x - edge.a.x) * edge.ux + (candidate.a.y - edge.a.y) * edge.uy;
    const endProjection = (candidate.b.x - edge.a.x) * edge.ux + (candidate.b.y - edge.a.y) * edge.uy;
    const start = Math.max(0, Math.min(startProjection, endProjection));
    const end = Math.min(edge.length, Math.max(startProjection, endProjection));
    return end - start > 0.001 ? { start, end } : null;
  }

  function mergeIntervals(intervals, edgeLength) {
    if (!intervals.length) return [];
    intervals.sort((left, right) => left.start - right.start);
    const merged = [];
    for (const interval of intervals) {
      const normalized = {
        start: clamp(interval.start, 0, edgeLength),
        end: clamp(interval.end, 0, edgeLength)
      };
      const last = merged[merged.length - 1];
      if (!last || normalized.start > last.end + 0.001) merged.push(normalized);
      else last.end = Math.max(last.end, normalized.end);
    }
    return merged;
  }

  function fragmentOnEdge(edge, start, end) {
    return {
      a: { x: edge.a.x + edge.ux * start, y: edge.a.y + edge.uy * start },
      b: { x: edge.a.x + edge.ux * end, y: edge.a.y + edge.uy * end }
    };
  }

  function fragmentIdentity(fragment) {
    const a = `${Math.round(fragment.a.x * 1000)},${Math.round(fragment.a.y * 1000)}`;
    const b = `${Math.round(fragment.b.x * 1000)},${Math.round(fragment.b.y * 1000)}`;
    return a < b ? `${a}|${b}` : `${b}|${a}`;
  }

  function showCanvasMessage(title, body, kind = 'loading') {
    dom.canvasMessageTitle.textContent = title;
    dom.canvasMessageBody.textContent = body;
    dom.canvasMessage.dataset.kind = kind;
    dom.canvasMessage.dataset.visible = 'true';
  }

  function hideCanvasMessage() {
    dom.canvasMessage.dataset.visible = 'false';
    dom.canvasMessage.dataset.kind = 'loading';
  }

  function showToast(message, kind = 'success') {
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.dataset.kind = kind;
    toast.textContent = message;
    dom.toastRegion.appendChild(toast);
    window.setTimeout(() => toast.remove(), 4300);
  }

  function setProtocolStatus(message) {
    dom.protocolStatus.textContent = message;
  }

  function normalizePolygon(points) {
    if (!Array.isArray(points)) return [];
    return points.map(normalizePoint).filter(Boolean);
  }

  function normalizePoint(point) {
    if (Array.isArray(point) && point.length >= 2) {
      const x = Number(point[0]);
      const y = Number(point[1]);
      return Number.isFinite(x) && Number.isFinite(y) ? { x, y } : null;
    }
    if (!point || typeof point !== 'object') return null;
    const x = Number(point.x);
    const y = Number(point.y);
    return Number.isFinite(x) && Number.isFinite(y) ? { x, y } : null;
  }

  function polygonArea(polygon) {
    if (!polygon || polygon.length < 3) return 0;
    let area = 0;
    for (let index = 0; index < polygon.length; index += 1) {
      const current = polygon[index];
      const next = polygon[(index + 1) % polygon.length];
      area += current.x * next.y - next.x * current.y;
    }
    return Math.abs(area) / 2;
  }

  function polygonCentroid(polygon) {
    if (!polygon.length) return { x: 0, y: 0 };
    let x = 0;
    let y = 0;
    for (const point of polygon) {
      x += point.x;
      y += point.y;
    }
    return { x: x / polygon.length, y: y / polygon.length };
  }

  function polygonBounds(polygon) {
    if (!polygon.length) return null;
    const bounds = { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity };
    for (const point of polygon) {
      bounds.minX = Math.min(bounds.minX, point.x);
      bounds.minY = Math.min(bounds.minY, point.y);
      bounds.maxX = Math.max(bounds.maxX, point.x);
      bounds.maxY = Math.max(bounds.maxY, point.y);
    }
    return bounds;
  }

  function unionBounds(left, right) {
    if (!right) return left;
    if (!left) return { ...right };
    return {
      minX: Math.min(left.minX, right.minX),
      minY: Math.min(left.minY, right.minY),
      maxX: Math.max(left.maxX, right.maxX),
      maxY: Math.max(left.maxY, right.maxY)
    };
  }

  function worldToScreenX(x) {
    return x * view.zoom + view.panX;
  }

  function worldToScreenY(y) {
    return y * view.zoom + view.panY;
  }

  function screenToWorld(x, y) {
    return { x: (x - view.panX) / view.zoom, y: (y - view.panY) / view.zoom };
  }

  function viewportWorldBounds(paddingPixels = 0) {
    const topLeft = screenToWorld(-paddingPixels, -paddingPixels);
    const bottomRight = screenToWorld(view.width + paddingPixels, view.height + paddingPixels);
    return {
      minX: Math.min(topLeft.x, bottomRight.x),
      minY: Math.min(topLeft.y, bottomRight.y),
      maxX: Math.max(topLeft.x, bottomRight.x),
      maxY: Math.max(topLeft.y, bottomRight.y)
    };
  }

  function boundsIntersect(left, right) {
    if (!left || !right) return false;
    return !(
      left.maxX < right.minX ||
      left.minX > right.maxX ||
      left.maxY < right.minY ||
      left.minY > right.maxY
    );
  }

  function pointInsideBounds(point, bounds) {
    return Boolean(
      point &&
      bounds &&
      point.x >= bounds.minX &&
      point.x <= bounds.maxX &&
      point.y >= bounds.minY &&
      point.y <= bounds.maxY
    );
  }

  function pointDistance(a, b) {
    return Math.hypot(a.x - b.x, a.y - b.y);
  }

  function midpointOf(a, b) {
    return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
  }

  function roundedRectPath(ctx, x, y, width, height, radius) {
    const r = Math.min(radius, width / 2, height / 2);
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + width - r, y);
    ctx.quadraticCurveTo(x + width, y, x + width, y + r);
    ctx.lineTo(x + width, y + height - r);
    ctx.quadraticCurveTo(x + width, y + height, x + width - r, y + height);
    ctx.lineTo(x + r, y + height);
    ctx.quadraticCurveTo(x, y + height, x, y + height - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
  }

  function niceDistance(rawDistance) {
    if (!Number.isFinite(rawDistance) || rawDistance <= 0) return 1;
    const exponent = 10 ** Math.floor(Math.log10(rawDistance));
    const normalized = rawDistance / exponent;
    if (normalized <= 1) return exponent;
    if (normalized <= 2) return 2 * exponent;
    if (normalized <= 5) return 5 * exponent;
    return 10 * exponent;
  }

  function formatDistance(value) {
    if (value === 0) return '0';
    if (Math.abs(value) < 1) return Number(value.toFixed(2)).toString();
    return Number(value.toFixed(1)).toString();
  }

  function formatArea(value) {
    return `${Math.round(finiteOr(value, 0)).toLocaleString()} m²`;
  }

  function formatPercent(ratio) {
    return `${Math.round(clamp(finiteOr(ratio, 0), 0, 9.99) * 100)}%`;
  }

  function formatDecimal(value, digits) {
    return finiteOr(value, 0).toFixed(digits);
  }

  function padMetric(value) {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? String(Math.max(0, Math.round(numeric))).padStart(3, '0') : String(value ?? '—');
  }

  function finiteOr(value, fallback) {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : fallback;
  }

  function createPolygonSVG(poly, category, size = 28) {
    const points = normalizePolygon(poly);
    if (points.length < 3) {
      return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
        <rect width="${size}" height="${size}" rx="6" fill="#2d3d32" />
        <text x="50%" y="55%" dominant-baseline="middle" text-anchor="middle" fill="#77837a" font-size="12" font-family="sans-serif">?</text>
      </svg>`;
    }
    
    let minX = Infinity, minY = Infinity;
    let maxX = -Infinity, maxY = -Infinity;
    for (const p of points) {
      if (p.x < minX) minX = p.x;
      if (p.y < minY) minY = p.y;
      if (p.x > maxX) maxX = p.x;
      if (p.y > maxY) maxY = p.y;
    }
    
    const width = maxX - minX;
    const height = maxY - minY;
    const maxDim = Math.max(width, height, 0.001);
    const padding = 4;
    const boxSize = 40;
    const scale = (boxSize - padding * 2) / maxDim;
    
    const scaledPoints = points.map(p => {
      const sx = padding + (p.x - minX) * scale;
      const sy = padding + (maxY - p.y) * scale;
      return `${sx.toFixed(1)},${sy.toFixed(1)}`;
    });
    
    const color = CATEGORY_COLORS[category] || CATEGORY_COLORS.room;
    
    return `<svg width="${size}" height="${size}" viewBox="0 0 ${boxSize} ${boxSize}" style="display: block; border-radius: 6px; overflow: hidden;">
      <rect width="${boxSize}" height="${boxSize}" fill="#131915" />
      <polygon points="${scaledPoints.join(' ')}" fill="${color}" stroke="rgba(248, 246, 239, 0.2)" stroke-width="1.5" stroke-linejoin="round" />
    </svg>`;
  }

  function toggleMerging() {
    if (!state.connected || !state.hasSite || state.trainingWanted) return;
    state.disableMerging = !state.disableMerging;
    state.placementRevision += 1;
    
    if (state.phase === 'paused' || state.phase === 'complete') {
      reloadPausedPlacements();
    }
    
    scheduleWallCache();
    updateMergingButton();
    updateDictionaryUI();
    requestRender();
  }

  function updateMergingButton() {
    if (!dom.toggleMergingBtn) return;
    const title = dom.toggleMergingBtn.querySelector('strong');
    const detail = dom.toggleMergingBtn.querySelector('small');
    if (state.disableMerging) {
      dom.toggleMergingBtn.classList.add('action-primary');
      if (title) title.textContent = 'Enable Merging (M)';
      if (detail) detail.textContent = 'Show merged shapes';
    } else {
      dom.toggleMergingBtn.classList.remove('action-primary');
      if (title) title.textContent = 'Disable Merging (M)';
      if (detail) detail.textContent = 'Show original shapes';
    }
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  window.addEventListener('beforeunload', () => {
    state.manuallyClosed = true;
    clearTimeout(state.reconnectTimer);
    clearTimeout(state.siteMetricTimer);
    if (state.developerUpdateFrame !== null) window.cancelAnimationFrame(state.developerUpdateFrame);
    cancelWallJob();
    if (state.socket) state.socket.close();
  });

  init();
})();
