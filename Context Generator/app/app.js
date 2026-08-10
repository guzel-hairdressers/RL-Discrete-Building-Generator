// Client-Side Dataset & Filter Application Controller
let allSites = [];
let filteredSites = [];
let currentIndex = 0;

// Application State Filters (S TIER PRESELECTED BY DEFAULT)
const state = {
  activeTier: 'S',
  minArea: 600,
  maxArea: 1200,
  city: 'ALL',
  minHeight: 10,
  maxHeight: 300
};

// Tier Range Definitions (XS, S, M, L, XL)
const TIER_RANGES = {
  XS: [150, 600],
  S:  [600, 1200],
  M:  [1200, 2500],
  L:  [2500, 4500],
  XL: [4000, 10000]
};

document.addEventListener('DOMContentLoaded', async () => {
  await fetchDataset();
  setupEventListeners();
  applyFilters();
});

async function fetchDataset() {
  try {
    const res = await fetch('../dataset/master_urban_dataset.json');
    allSites = await res.json();
    console.log(`Loaded ${allSites.length} site records from master_urban_dataset.json`);
  } catch (err) {
    console.error('Failed to load master_urban_dataset.json:', err);
  }
}

function setupEventListeners() {
  // Small Tier Preset Buttons Right-Aligned (XS, S, M, L, XL)
  document.querySelectorAll('.tier-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.tier-btn').forEach(b => b.classList.remove('active'));
      e.target.classList.add('active');
      
      const tier = e.target.dataset.tier;
      state.activeTier = tier;
      
      if (TIER_RANGES[tier]) {
        state.minArea = TIER_RANGES[tier][0];
        state.maxArea = TIER_RANGES[tier][1];
        
        document.getElementById('range-area-min').value = state.minArea;
        document.getElementById('range-area-max').value = state.maxArea;
        updateAreaSliderUI();
      }
      
      applyFilters();
    });
  });

  // Site Area Range Sliders
  const rangeAreaMin = document.getElementById('range-area-min');
  const rangeAreaMax = document.getElementById('range-area-max');
  
  rangeAreaMin.addEventListener('input', (e) => {
    state.minArea = parseInt(e.target.value);
    if (state.minArea > state.maxArea) {
      state.maxArea = state.minArea;
      rangeAreaMax.value = state.maxArea;
    }
    state.activeTier = null;
    document.querySelectorAll('.tier-btn').forEach(b => b.classList.remove('active'));
    updateAreaSliderUI();
    applyFilters();
  });

  rangeAreaMax.addEventListener('input', (e) => {
    state.maxArea = parseInt(e.target.value);
    if (state.maxArea < state.minArea) {
      state.minArea = state.maxArea;
      rangeAreaMin.value = state.minArea;
    }
    state.activeTier = null;
    document.querySelectorAll('.tier-btn').forEach(b => b.classList.remove('active'));
    updateAreaSliderUI();
    applyFilters();
  });

  // City Selector Dropdown
  document.getElementById('select-city').addEventListener('change', (e) => {
    state.city = e.target.value;
    applyFilters();
  });

  // Context Height Range Sliders
  const rangeHeightMin = document.getElementById('range-height-min');
  const rangeHeightMax = document.getElementById('range-height-max');

  rangeHeightMin.addEventListener('input', (e) => {
    state.minHeight = parseInt(e.target.value);
    if (state.minHeight > state.maxHeight) {
      state.maxHeight = state.minHeight;
      rangeHeightMax.value = state.maxHeight;
    }
    updateHeightSliderUI();
    applyFilters();
  });

  rangeHeightMax.addEventListener('input', (e) => {
    state.maxHeight = parseInt(e.target.value);
    if (state.maxHeight < state.minHeight) {
      state.minHeight = state.maxHeight;
      rangeHeightMin.value = state.minHeight;
    }
    updateHeightSliderUI();
    applyFilters();
  });

  // Clean Reset Button
  document.getElementById('btn-reset-filters').addEventListener('click', () => {
    resetFilters();
  });

  // Carousel Side Arrows
  document.getElementById('btn-prev-site').addEventListener('click', () => navigateCarousel(-1));
  document.getElementById('btn-next-site').addEventListener('click', () => navigateCarousel(1));

  // Random Site Action
  document.getElementById('btn-random-site').addEventListener('click', () => pickRandomSite());

  // Keyboard Shortcuts (Arrow Left & Arrow Right)
  window.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft') navigateCarousel(-1);
    if (e.key === 'ArrowRight') navigateCarousel(1);
  });
}

function updateAreaSliderUI() {
  document.getElementById('val-area-summary').innerText = `${state.minArea} m² - ${state.maxArea} m²`;
}

function updateHeightSliderUI() {
  document.getElementById('val-height-summary').innerText = `${state.minHeight}m - ${state.maxHeight}m`;
}

function resetFilters() {
  state.activeTier = 'S';
  state.minArea = 600;
  state.maxArea = 1200;
  state.city = 'ALL';
  state.minHeight = 10;
  state.maxHeight = 300;

  document.querySelectorAll('.tier-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.tier === 'S');
  });

  document.getElementById('range-area-min').value = 600;
  document.getElementById('range-area-max').value = 1200;
  document.getElementById('select-city').value = 'ALL';
  document.getElementById('range-height-min').value = 10;
  document.getElementById('range-height-max').value = 300;

  updateAreaSliderUI();
  updateHeightSliderUI();
  applyFilters();
}

function applyFilters() {
  filteredSites = allSites.filter(site => {
    // Site Area filter
    if (site.site_area_m2 < state.minArea || site.site_area_m2 > state.maxArea) return false;
    
    // City filter
    if (state.city !== 'ALL' && site.city_code !== state.city) return false;
    
    // Context Height filter
    const avgH = site.avg_height_m || 0;
    if (avgH < state.minHeight || avgH > state.maxHeight) return false;

    return true;
  });

  console.log(`Filtered: ${filteredSites.length} / ${allSites.length} sites match filters.`);
  currentIndex = 0;
  updateSiteDisplay();
}

function navigateCarousel(delta) {
  if (filteredSites.length === 0) return;
  currentIndex = (currentIndex + delta + filteredSites.length) % filteredSites.length;
  updateSiteDisplay();
}

function pickRandomSite() {
  if (filteredSites.length === 0) return;
  currentIndex = Math.floor(Math.random() * filteredSites.length);
  updateSiteDisplay();
}

function updateSiteDisplay() {
  const bottomCounter = document.getElementById('match-counter-text');
  
  if (filteredSites.length === 0) {
    bottomCounter.innerText = `0 of 0`;
    updateSiteInfoCard(null);
    return;
  }

  const currentSite = filteredSites[currentIndex];
  // Update bottom counter ("Site 3 of 42", without the word "matching")
  bottomCounter.innerText = `Site ${currentIndex + 1} of ${filteredSites.length}`;
  
  updateSiteInfoCard(currentSite);

  // Load 3D WebGL context into Three.js engine
  if (window.ThreeEngine) {
    window.ThreeEngine.loadSiteContext(currentSite);
  }
}

function updateSiteInfoCard(site) {
  if (!site) {
    document.getElementById('site-city-title').innerText = "No Sites Match Filters";
    return;
  }

  document.getElementById('site-city-title').innerText = site.city_name || site.city_code.toUpperCase();
  document.getElementById('site-coords').innerText = `Lat: ${site.lat?.toFixed(4) || '--'}, Lon: ${site.lon?.toFixed(4) || '--'}`;
  document.getElementById('val-area').innerText = `${site.site_area_m2?.toFixed(1) || '--'} m²`;
  document.getElementById('val-tier').innerText = `${site.area_tier} Tier`;
  document.getElementById('val-far').innerText = site.far?.toFixed(2) || '2.50';
  document.getElementById('val-bldgs').innerText = site.building_count || '--';
  document.getElementById('val-height-range').innerText = `${site.avg_height_m?.toFixed(1) || 0}m | ${site.max_height_m?.toFixed(1) || 0}m`;
  
  const avgStoreys = Math.round((site.avg_height_m || 0) / 3.2);
  const maxStoreys = Math.round((site.max_height_m || 0) / 3.2);
  document.getElementById('val-storeys-range').innerText = `${avgStoreys} | ${maxStoreys}`;
}
