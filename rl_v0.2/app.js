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

let ws;
let isTraining = true;
let isReady = false;
let placements = [];
let boundaries = [];
let holes = [];
let dictionary = [];
let scoreHistory = [];
let bestScore = 0;
let metrics = { fillRatio: 0, rentableRatio: 0, score: 0 };
let currentEpisode = 0;
let currentStep = 0;
let scale = 14;
let offsetX = 0;
let offsetY = 0;
let isPanning = false;
let startX, startY;
let targetZoom = 14;

// Colors matching previous clean styles
const COLORS = {
  room: '#d8dfd6',
  special: '#b0c0a8',
  corridor: '#e4cf87',
  core: '#c9816d'
};

function setup() {
  const canvas = createCanvas(windowWidth - 360, windowHeight);
  canvas.parent('planCanvasContainer');
  offsetX = width / 2 - 20 * scale;
  offsetY = height / 2 - 14 * scale;
  
  // Set up WebSockets
  connectWebSocket();
  
  // Set up inputs synchronization
  setupParameterSync();
}

function connectWebSocket() {
  ws = new WebSocket('ws://localhost:8000/ws');
  
  ws.onopen = () => {
    document.getElementById('statusDot').style.backgroundColor = '#718531';
    document.getElementById('statusText').innerText = 'Connected to PyTorch GPU';
    document.getElementById('canvasEmpty').style.display = 'none';
    
    // Trigger first site load
    sendSettings();
    ws.send(JSON.stringify({ cmd: 'newSite' }));
  };
  
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    if (data.type === 'site') {
      boundaries = data.boundaries || [];
      dictionary = data.dictionary || [];
      placements = [];
      currentStep = 0;
      isReady = true; // Unlock step requests
      
      // Update GPU/Device status
      const dev = data.device || 'cpu';
      document.getElementById('deviceStatus').innerText = `Device: ${dev.toUpperCase()}`;
      if (dev.toLowerCase() === 'cpu') {
        document.getElementById('deviceStatus').style.color = '#d16a50'; // highlight CPU warnings
      } else {
        document.getElementById('deviceStatus').style.color = '#7ba368'; // success green for GPU/MPS
      }
      
      updateDictionaryUI();
    } else if (data.type === 'placements') {
      data.placements.forEach(p => placements.push(p));
      currentStep = placements.length;
      updateMetricsUI();
    } else if (data.type === 'episodeDone') {
      metrics = data.metrics;
      scoreHistory = data.scoreHistory || [];
      bestScore = data.bestScore || 0;
      currentEpisode++;
      updateMetricsUI();
      
      // Request next episode site (lock stepping)
      isReady = false;
      if (isTraining) {
        placements = [];
        currentStep = 0;
        ws.send(JSON.stringify({ cmd: 'newSite' }));
      }
    } else if (data.type === 'ack') {
      if (data.msg === 'checkpoint saved') {
        alert("Success: Policy checkpoint saved to outputs/checkpoint.pt!");
      }
    }
  };
  
  ws.onclose = () => {
    isReady = false;
    document.getElementById('statusDot').style.backgroundColor = '#d16a50';
    document.getElementById('statusText').innerText = 'Disconnected (Server Offline)';
    document.getElementById('canvasEmpty').style.display = 'flex';
  };
}

function sendSettings() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    const settings = {
      boundaryType: document.getElementById('boundaryType').value,
      atriumPolicy: document.getElementById('atriumPolicy').value,
      singleFloor: document.getElementById('singleFloor').checked,
      publicMode: document.getElementById('publicMode').checked,
      minEdge: parseFloat(document.getElementById('minEdge').value),
      maxEdge: parseFloat(document.getElementById('maxEdge').value),
      maxEdges: parseInt(document.getElementById('maxEdges').value),
      dictCap: parseInt(document.getElementById('dictCap').value),
      angleStep: parseFloat(document.getElementById('angleStep').value),
      maxModules: parseInt(document.getElementById('maxModules').value),
      travelLimit: parseFloat(document.getElementById('travelLimit').value),
      learningRate: parseFloat(document.getElementById('learningRate').value)
    };
    ws.send(JSON.stringify({ cmd: 'updateSettings', settings }));
  }
}

function setupParameterSync() {
  const sliders = document.querySelectorAll('#controls input[type="range"]');
  sliders.forEach(slider => {
    const numInput = document.getElementById(slider.id + 'Num');
    if (numInput) {
      // Sync slider -> number
      slider.addEventListener('input', () => {
        numInput.value = slider.value;
        sendSettings();
      });
      // Sync number -> slider
      numInput.addEventListener('input', () => {
        slider.value = numInput.value;
        sendSettings();
      });
    }
  });
  
  document.getElementById('boundaryType').addEventListener('change', () => {
    isReady = false;
    sendSettings();
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ cmd: 'newSite' }));
  });
  document.getElementById('atriumPolicy').addEventListener('change', sendSettings);
  document.getElementById('singleFloor').addEventListener('change', sendSettings);
  document.getElementById('publicMode').addEventListener('change', () => {
    isReady = false;
    sendSettings();
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ cmd: 'newSite' }));
  });
  
  // Buttons
  document.getElementById('trainBtn').addEventListener('click', () => {
    isTraining = !isTraining;
    document.getElementById('trainBtn').innerText = isTraining ? 'Pause training' : 'Resume training';
  });
  
  document.getElementById('newSiteBtn').addEventListener('click', () => {
    isReady = false;
    isTraining = false; // Pause training so the user sees the empty canvas first!
    document.getElementById('trainBtn').innerText = 'Resume training';
    placements = [];
    boundaries = [];
    currentStep = 0;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ cmd: 'newSite' }));
    }
  });
  
  document.getElementById('resetPolicyBtn').addEventListener('click', () => {
    isReady = false;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ cmd: 'resetPolicy' }));
    }
  });

  document.getElementById('saveCheckpointBtn').addEventListener('click', () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ cmd: 'saveCheckpoint' }));
    }
  });
}

function draw() {
  background('#f3f1eb');
  
  // Smooth Zoom interpolation
  scale = lerp(scale, targetZoom, 0.12);
  
  push();
  translate(offsetX, offsetY);
  
  // Draw Coordinate Grid
  stroke('#e4e2db');
  strokeWeight(0.5);
  for (let x = -100; x < 200; x += 1) {
    line(x * scale, -100 * scale, x * scale, 200 * scale);
  }
  for (let y = -100; y < 200; y += 1) {
    line(-100 * scale, y * scale, 200 * scale, y * scale);
  }
  
  // Draw Site Boundaries (2x2 Parallel Grid with cutout holes)
  if (boundaries) {
    fill('#faf9f5');
    stroke('#171a16');
    strokeWeight(2.5);
    boundaries.forEach((b, idx) => {
      beginShape();
      // Outer boundary vertices
      b.outer.forEach(p => vertex(p.x * scale, p.y * scale));
      
      // Contours for cutout holes (drawn in reverse winding order)
      if (b.holes && b.holes.length > 0) {
        b.holes.forEach(hole => {
          beginContour();
          for (let k = hole.length - 1; k >= 0; k--) {
            vertex(hole[k].x * scale, hole[k].y * scale);
          }
          endContour();
        });
      }
      endShape(CLOSE);

      // Draw Site Labels and Areas under each boundary
      const outerArea = G_polyArea(b.outer);
      const holesArea = b.holes ? b.holes.reduce((sum, h) => sum + G_polyArea(h), 0) : 0;
      const netSiteArea = outerArea - holesArea;

      const instancePlacements = placements.filter(p => p.instanceIdx === idx);
      const netFilledArea = instancePlacements.reduce((sum, p) => sum + G_polyArea(p.poly), 0);

      // Find bounding box to place label nicely
      let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
      b.outer.forEach(p => {
        if (p.x < minX) minX = p.x;
        if (p.x > maxX) maxX = p.x;
        if (p.y < minY) minY = p.y;
        if (p.y > maxY) maxY = p.y;
      });

      push();
      fill('#252a22');
      noStroke();
      textSize(Math.max(6, scale * 0.4));
      textAlign(CENTER, TOP);
      text(
        `SITE ${idx + 1} — Site: ${Math.round(netSiteArea)}m² | Filled: ${Math.round(netFilledArea)}m²`,
        ((minX + maxX) / 2) * scale,
        (maxY + 1.2) * scale
      );
      pop();
    });
  }
  
  // Draw Atriums (Outlines around cutouts)
  noFill();
  stroke('#171a16');
  strokeWeight(2.5);
  boundaries.forEach(b => {
    if (b.holes) {
      b.holes.forEach(hole => {
        beginShape();
        hole.forEach(p => vertex(p.x * scale, p.y * scale));
        endShape(CLOSE);
      });
    }
  });
  
  // Draw Placed Modules (Category fills, no outlines)
  placements.forEach(placement => {
    const cat = placement.module.category;
    fill(COLORS[cat] || '#e0e0e0');
    noStroke();
    beginShape();
    placement.poly.forEach(p => vertex(p.x * scale, p.y * scale));
    endShape(CLOSE);
  });
  
  // Draw Vector Wall Outlines (Thick outer envelope, thin inner separators)
  placements.forEach(p1 => {
    const poly = p1.poly;
    const n = poly.length;
    for (let i = 0; i < n; i++) {
      const a = poly[i];
      const b = poly[(i + 1) % n];
      
      const ax = b.x - a.x, ay = b.y - a.y;
      const len = Math.hypot(ax, ay);
      if (len < 1e-4) continue;
      
      // Collect shared overlapping intervals
      let sharedIntervals = [];
      placements.forEach(p2 => {
        if (p1.id === p2.id) return;
        if (p1.instanceIdx !== p2.instanceIdx) return;
        
        const n2 = p2.poly.length;
        for (let j = 0; j < n2; j++) {
          const c = p2.poly[j];
          const d = p2.poly[(j + 1) % n2];
          const interval = G_getOverlapInterval(a, b, len, c, d);
          if (interval) {
            sharedIntervals.push(interval);
          }
        }
      });
      
      // Merge overlapping shared intervals
      sharedIntervals.sort((i1, i2) => i1.min - i2.min);
      let mergedShared = [];
      sharedIntervals.forEach(interval => {
        if (mergedShared.length === 0) {
          mergedShared.push(interval);
        } else {
          let last = mergedShared[mergedShared.length - 1];
          if (interval.min <= last.max + 0.02) { // 2cm tolerance
            last.max = Math.max(last.max, interval.max);
          } else {
            mergedShared.push(interval);
          }
        }
      });
      
      // Draw sections sequentially
      let current = 0;
      mergedShared.forEach(shared => {
        // Draw unshared part (outer wall)
        if (shared.min - current > 0.02) {
          stroke('#171a16');
          strokeWeight(3.5);
          lineOnInterval(current, shared.min);
        }
        // Draw shared part (thin interior separator)
        stroke('#a0a29a');
        strokeWeight(1);
        lineOnInterval(shared.min, shared.max);
        current = shared.max;
      });
      
      // Draw remaining unshared part (outer wall)
      if (len - current > 0.02) {
        stroke('#171a16');
        strokeWeight(3.5);
        lineOnInterval(current, len);
      }
      
      function lineOnInterval(t1, t2) {
        const x1 = a.x + (ax / len) * t1;
        const y1 = a.y + (ay / len) * t1;
        const x2 = a.x + (ax / len) * t2;
        const y2 = a.y + (ay / len) * t2;
        line(x1 * scale, y1 * scale, x2 * scale, y2 * scale);
      }
    }
    
    // Label
    fill('#252a22');
    noStroke();
    textSize(Math.max(6, scale * 0.5));
    textAlign(CENTER, CENTER);
    text(p1.module.id, p1.center.x * scale, p1.center.y * scale);
  });

  // Draw Space Syntax Connectivity Graph Overlay
  stroke('rgba(23, 26, 22, 0.45)');
  strokeWeight(1.5);
  drawingContext.setLineDash([3, 4]); // Dotted lines
  for (let i = 0; i < placements.length; i++) {
    const p1 = placements[i];
    for (let j = i + 1; j < placements.length; j++) {
      const p2 = placements[j];
      if (p1.instanceIdx !== p2.instanceIdx) continue;
      
      let connected = false;
      const poly1 = p1.poly, poly2 = p2.poly;
      for (let idx1 = 0; idx1 < poly1.length; idx1++) {
        const a1 = poly1[idx1], a2 = poly1[(idx1 + 1) % poly1.length];
        if (G_segmentSharedWithPoly(a1, a2, poly2)) {
          connected = true;
          break;
        }
      }
      
      if (connected) {
        line(p1.center.x * scale, p1.center.y * scale, p2.center.x * scale, p2.center.y * scale);
      }
    }
  }
  drawingContext.setLineDash([]); // Reset
  
  // Draw nodes at centroids
  placements.forEach(p => {
    noStroke();
    if (p.module.category === 'core') fill('#d16a50');
    else if (p.module.category === 'corridor') fill('#d5bb63');
    else fill('#718531');
    circle(p.center.x * scale, p.center.y * scale, 6);
  });
  
  pop();
  
  // Step training if running and websocket is ready
  if (isReady && isTraining && ws && ws.readyState === WebSocket.OPEN && frameCount % Math.max(1, Math.floor(100 / document.getElementById('speed').value)) === 0) {
    ws.send(JSON.stringify({ cmd: 'step' }));
  }
  
  // Draw Staggered Geographic Scale Bar
  drawScaleBar();
}

function drawScaleBar() {
  const barWidth = 100;
  const pixelsPerMeter = scale;
  const maxMeters = barWidth / pixelsPerMeter;
  
  // Staggered increments: 0, 1, 2, 5, 10
  let step = 1;
  if (maxMeters > 50) step = 10;
  else if (maxMeters > 20) step = 5;
  else if (maxMeters > 8) step = 2;
  else if (maxMeters > 4) step = 1;
  else step = 0.5;
  
  const x = width - 150;
  const y = height - 50;
  
  stroke('#252a22');
  strokeWeight(1.5);
  line(x, y, x + step * 5 * scale, y);
  
  // Draw staggered ticks
  for (let i = 0; i <= 5; i++) {
    const tx = x + i * step * scale;
    line(tx, y, tx, y - 5);
    
    fill('#252a22');
    noStroke();
    textSize(8);
    textAlign(CENTER, BOTTOM);
    if (i === 0 || i === 1 || i === 2 || i === 5) {
      text((i * step) + 'm', tx, y - 8);
    }
  }
}

function updateMetricsUI() {
  let totalSiteArea = 0;
  let totalFilledArea = 0;
  let totalRentableArea = 0;
  
  if (boundaries && boundaries.length > 0) {
    boundaries.forEach((b, idx) => {
      const outerArea = G_polyArea(b.outer);
      const holesArea = b.holes ? b.holes.reduce((sum, h) => sum + G_polyArea(h), 0) : 0;
      const siteArea = outerArea - holesArea;
      totalSiteArea += siteArea;
      
      const instancePlacements = placements.filter(p => p.instanceIdx === idx);
      const filledArea = instancePlacements.reduce((sum, p) => sum + G_polyArea(p.poly), 0);
      totalFilledArea += filledArea;
      
      const rentableArea = instancePlacements
        .filter(p => p.module.category === 'room' || p.module.category === 'special')
        .reduce((sum, p) => sum + G_polyArea(p.poly), 0);
      totalRentableArea += rentableArea;
    });
  }
  
  const fillRatio = totalSiteArea > 0 ? (totalFilledArea / totalSiteArea) : 0;
  const rentableRatio = totalFilledArea > 0 ? (totalRentableArea / totalFilledArea) : 0;
  
  document.getElementById('scoreValue').innerText = metrics.score.toFixed(1);
  document.getElementById('fillMetric').innerText = Math.round(fillRatio * 100) + '%';
  document.getElementById('rentableMetric').innerText = Math.round(rentableRatio * 100) + '%';
  document.getElementById('episodeValue').innerText = String(currentEpisode).padStart(3, '0');
  document.getElementById('stepValue').innerText = String(currentStep).padStart(3, '0');
  document.getElementById('siteAreaCaption').innerText = `TOTAL FILLED: ${Math.round(totalFilledArea)} m²  ·  TOTAL SITE: ${Math.round(totalSiteArea)} m²`;
  
  const delta = document.getElementById('scoreDelta');
  if (bestScore > 0) {
    delta.innerText = `BEST ${bestScore.toFixed(1)}`;
  }
}

function updateDictionaryUI() {
  const container = document.getElementById('moduleDictionary');
  container.innerHTML = '';
  document.getElementById('dictCount').innerText = `${dictionary.length} active module types`;
  
  dictionary.forEach(module => {
    const card = document.createElement('div');
    card.className = 'module-card';
    card.innerHTML = `
      <div class="module-id" style="background:${COLORS[module.category] || '#eee'}">${module.id}</div>
      <div class="module-details">
        <strong>${module.category.toUpperCase()}</strong>
        <span>Area: ${Math.round(G_polyArea(module.poly))}m²</span>
      </div>
    `;
    container.appendChild(card);
  });
}

function G_polyArea(poly) {
  let sum = 0;
  for (let i = 0; i < poly.length; i++) {
    let a = poly[i];
    let b = poly[(i + 1) % poly.length];
    sum += a.x * b.y - b.x * a.y;
  }
  return Math.abs(sum) / 2;
}

// Panning and Zooming Controls
function mousePressed() {
  if (mouseX < width) {
    isPanning = true;
    startX = mouseX - offsetX;
    startY = mouseY - offsetY;
  }
}

function mouseDragged() {
  if (isPanning) {
    offsetX = mouseX - startX;
    offsetY = mouseY - startY;
  }
}

function mouseReleased() {
  isPanning = false;
}

function mouseWheel(event) {
  if (mouseX < width) {
    targetZoom = constrain(targetZoom - event.delta * 0.015, 6, 45);
    return false; // prevent default scroll
  }
}

function windowResized() {
  resizeCanvas(windowWidth - 360, windowHeight);
}

function G_segmentSharedWithPoly(a, b, poly) {
  const n = poly.length;
  for (let i = 0; i < n; i++) {
    const c = poly[i];
    const d = poly[(i + 1) % n];
    const overlap = G_getSharedOverlap(a, b, c, d);
    if (overlap >= 0.48) { // 0.5m tolerance
      return true;
    }
  }
  return false;
}

function G_getSharedOverlap(a1, a2, b1, b2) {
  const ax = a2.x - a1.x, ay = a2.y - a1.y;
  const alen = Math.hypot(ax, ay);
  if (alen < 1e-6) return 0;
  
  const bx = b2.x - b1.x, by = b2.y - b1.y;
  const blen = Math.hypot(bx, by);
  if (blen < 1e-6) return 0;
  
  const cross = ax * by - ay * bx;
  if (Math.abs(cross) / (alen * blen) > 0.05) return 0;
  
  const lineCross = (b1.x - a1.x) * ay - (b1.y - a1.y) * ax;
  if (Math.abs(lineCross) / alen > 0.05) return 0;
  
  const t_b1 = ((b1.x - a1.x) * ax + (b1.y - a1.y) * ay) / (alen * alen);
  const t_b2 = ((b2.x - a1.x) * ax + (b2.y - a1.y) * ay) / (alen * alen);
  
  const t_min = Math.max(0.0, Math.min(t_b1, t_b2));
  const t_max = Math.min(1.0, Math.max(t_b1, t_b2));
  
  if (t_max - t_min > 0.01) {
    return (t_max - t_min) * alen;
  }
  return 0;
}

function G_getOverlapInterval(a1, a2, alen, b1, b2) {
  const ax = a2.x - a1.x, ay = a2.y - a1.y;
  const bx = b2.x - b1.x, by = b2.y - b1.y;
  const blen = Math.hypot(bx, by);
  if (blen < 1e-6) return null;
  
  const cross = ax * by - ay * bx;
  if (Math.abs(cross) / (alen * blen) > 0.05) return null; // not parallel
  
  const lineCross = (b1.x - a1.x) * ay - (b1.y - a1.y) * ax;
  if (Math.abs(lineCross) / alen > 0.05) return null; // not collinear
  
  const t_b1 = ((b1.x - a1.x) * ax + (b1.y - a1.y) * ay) / (alen * alen);
  const t_b2 = ((b2.x - a1.x) * ax + (b2.y - a1.y) * ay) / (alen * alen);
  
  const t_min = Math.max(0.0, Math.min(t_b1, t_b2));
  const t_max = Math.min(1.0, Math.max(t_b1, t_b2));
  
  if (t_max - t_min > 0.01) {
    return { min: t_min * alen, max: t_max * alen };
  }
  return null;
}
