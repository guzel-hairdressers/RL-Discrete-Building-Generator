(function () {
  'use strict';

  const G = window.ModGeometry;
  const canvas = document.getElementById('planCanvas');
  const context = canvas.getContext('2d');
  const stage = canvas.closest('.stage');
  const colors = { room:'#d8dfd6', corridor:'#e4cf87', core:'#c9816d', atrium:'#8eb9c1' };
  const dom = {};
  let agent;
  let training = false;
  let nextEpisodeAt = 0;
  let renderedEpisode = -1;
  let renderedStep = -1;
  let drag = null;
  let view = { scale: 16, offsetX: 0, offsetY: 0 };
  let cssWidth = 800;
  let cssHeight = 600;

  const ids = [
    'statusDot','statusText','newSiteBtn','trainBtn','trainIcon','trainLabel','boundaryType','atriumPolicy','singleFloor','lobeCount','lobeCountOut','boundaryVertices','boundaryVerticesOut','concavity','concavityOut','lobeReach','lobeReachOut',
    'minEdge','minEdgeOut','maxEdge','maxEdgeOut','maxEdges','maxEdgesOut','dictCap','dictCapOut','angleStep','orientationMode','allowShear',
    'maxModules','maxModulesOut','travelLimit','travelLimitOut','learningRate','learningRateOut','speed','speedOut',
    'resetPolicyBtn','episodeValue','stepValue','zoomOutBtn','fitBtn','zoomInBtn','canvasEmpty','scaleBar','siteAreaCaption','geometryAudit','orientationCaption',
    'scoreValue','scoreDelta','scoreSparkline','fillMetric','fillBar','areaMetric','moduleMetric','moduleLimitMetric','dictMetric',
    'reuseMetric','lightMetric','travelMetric','travelLimitMetric','rewardValue','qualityBars','dictCount','moduleDictionary','policyWeights'
  ];
  ids.forEach((id) => { dom[id] = document.getElementById(id); });

  function settingsFromUI() {
    return {
      boundaryType: dom.boundaryType.value,
      atriumPolicy: dom.atriumPolicy.value,
      singleFloor: dom.singleFloor.checked,
      lobeCount:Number(dom.lobeCount.value),
      boundaryVertices:Number(dom.boundaryVertices.value),
      concavity:Number(dom.concavity.value),
      lobeReach:Number(dom.lobeReach.value),
      minEdge: Number(dom.minEdge.value),
      maxEdge: Number(dom.maxEdge.value),
      maxEdges: Number(dom.maxEdges.value),
      dictCap: Number(dom.dictCap.value),
      angleStep: Number(dom.angleStep.value),
      orientationMode:dom.orientationMode.value,
      allowShear:dom.allowShear.checked,
      maxModules: Number(dom.maxModules.value),
      travelLimit: Number(dom.travelLimit.value),
      learningRate: Number(dom.learningRate.value),
      speed: Number(dom.speed.value)
    };
  }

  function updateControlOutputs() {
    dom.minEdgeOut.value = `${Number(dom.minEdge.value).toFixed(1)} m`;
    dom.maxEdgeOut.value = `${Number(dom.maxEdge.value).toFixed(1)} m`;
    dom.maxEdgesOut.value = dom.maxEdges.value;
    dom.dictCapOut.value = `${dom.dictCap.value} types`;
    dom.maxModulesOut.value = dom.maxModules.value;
    dom.travelLimitOut.value = `${dom.travelLimit.value} m`;
    dom.learningRateOut.value = Number(dom.learningRate.value).toFixed(2);
    dom.speedOut.value = `${dom.speed.value}×`;
    dom.lobeCountOut.value=dom.lobeCount.value;
    dom.boundaryVerticesOut.value=dom.boundaryVertices.value;
    dom.concavityOut.value=`${Math.round(Number(dom.concavity.value)*100)}%`;
    dom.lobeReachOut.value=`${Number(dom.lobeReach.value).toFixed(2)}×`;
  }

  function setTraining(active) {
    training = active;
    dom.trainIcon.textContent = active ? 'Ⅱ' : '▶';
    dom.trainLabel.textContent = active ? 'Pause training' : 'Train policy';
    dom.statusDot.className = `status-dot${active ? ' active' : agent.done ? ' complete' : ''}`;
    dom.statusText.textContent = active ? 'Policy learning' : agent.done ? 'Episode complete' : 'Ready to train';
    if (active && agent.done) {
      agent.newEpisode();
      renderedEpisode = -1;
    }
  }

  function rebuildEnvironment(newSite) {
    setTraining(false);
    agent.updateSettings(settingsFromUI());
    if (newSite) agent.newSite();
    else agent.resetEnvironment(false);
    fitView();
    renderedEpisode = -1;
    renderedStep = -1;
    updateUI(true);
    render();
  }

  function fitView() {
    if (!agent || !agent.site) return;
    const b = agent.site.bounds;
    const marginX = 72;
    const marginY = 82;
    const width = Math.max(1,b.maxX-b.minX);
    const height = Math.max(1,b.maxY-b.minY);
    view.scale = Math.min((cssWidth-marginX*2)/width,(cssHeight-marginY*2)/height);
    view.scale = G.clamp(view.scale, 7, 34);
    view.offsetX = cssWidth/2 - (b.minX+b.maxX)/2*view.scale;
    view.offsetY = cssHeight/2 - (b.minY+b.maxY)/2*view.scale;
    updateScaleBar();
  }

  function resizeCanvas() {
    const rect = stage.getBoundingClientRect();
    cssWidth = Math.max(1,Math.round(rect.width));
    cssHeight = Math.max(1,Math.round(rect.height));
    const dpr = Math.min(2,window.devicePixelRatio || 1);
    canvas.width = Math.round(cssWidth*dpr);
    canvas.height = Math.round(cssHeight*dpr);
    canvas.style.width = `${cssWidth}px`;
    canvas.style.height = `${cssHeight}px`;
    context.setTransform(dpr,0,0,dpr,0,0);
    fitView();
    render();
  }

  function screenPoint(point) { return { x:point.x*view.scale+view.offsetX, y:point.y*view.scale+view.offsetY }; }

  function pathPolygon(poly) {
    const path = new Path2D();
    poly.forEach((point,index) => {
      const p = screenPoint(point);
      if (index===0) path.moveTo(p.x,p.y);
      else path.lineTo(p.x,p.y);
    });
    path.closePath();
    return path;
  }

  function siteCompoundPath() {
    const path=pathPolygon(agent.site.outer);
    agent.site.holes.forEach((hole)=>path.addPath(pathPolygon(hole)));
    return path;
  }

  function renderSite() {
    const sitePath=siteCompoundPath();
    context.save();
    context.shadowColor='rgba(31,37,28,.14)';
    context.shadowBlur=24;
    context.shadowOffsetY=9;
    context.fillStyle = 'rgba(250,249,245,.94)';
    context.fill(sitePath,'evenodd');
    context.restore();

    agent.site.holes.forEach((hole) => {
      const holePath = pathPolygon(hole);
      context.fillStyle = 'rgba(158,201,212,.34)';
      context.fill(holePath);
      context.save();
      context.clip(holePath);
      context.strokeStyle = 'rgba(61,95,102,.25)';
      context.lineWidth = 1;
      const hb = G.boundsOf(hole);
      const start = screenPoint({x:hb.minX-8,y:hb.minY-8});
      const end = screenPoint({x:hb.maxX+8,y:hb.maxY+8});
      for (let x=start.x-end.y+start.y;x<end.x+end.y-start.y;x+=8) {
        context.beginPath();
        context.moveTo(x,start.y);
        context.lineTo(x+(end.y-start.y),end.y);
        context.stroke();
      }
      context.restore();
    });
  }

  function renderSiteOutline() {
    agent.site.holes.forEach((hole)=>{
      context.strokeStyle='#557a81';
      context.lineWidth=1.5;
      context.setLineDash([4,3]);
      context.stroke(pathPolygon(hole));
      context.setLineDash([]);
      const center=screenPoint(G.polygonCentroid(hole));
      context.fillStyle='#365c63';
      context.textAlign='center';
      context.textBaseline='middle';
      context.font="500 7px 'DM Mono', monospace";
      context.fillText('LIGHT COURT',center.x,center.y-4);
      context.font="500 6px 'DM Mono', monospace";
      context.fillText(`${G.polygonArea(hole).toFixed(0)} m²`,center.x,center.y+5);
    });
    context.strokeStyle = '#161915';
    context.lineWidth = 2.6;
    context.stroke(pathPolygon(agent.site.outer));
  }

  function renderOrientationBasis(){
    const center=screenPoint(G.polygonCentroid(agent.site.outer));
    const angle=agent.episodeOrientation*Math.PI/180;
    const length=Math.min(cssWidth,cssHeight)*.28;
    context.save();
    context.strokeStyle='rgba(113,133,49,.3)';
    context.lineWidth=1;
    context.setLineDash([3,5]);
    [angle,angle+Math.PI/2].forEach((axis)=>{
      context.beginPath();
      context.moveTo(center.x-Math.cos(axis)*length,center.y-Math.sin(axis)*length);
      context.lineTo(center.x+Math.cos(axis)*length,center.y+Math.sin(axis)*length);
      context.stroke();
    });
    context.restore();
  }

  function renderPlacements(now) {
    agent.placements.forEach((placement,index) => {
      const path = pathPolygon(placement.poly);
      const age = Math.min(1,(now-placement.bornAt)/160);
      context.save();
      context.globalAlpha = .3+.7*age;
      context.fillStyle = colors[placement.module.category];
      context.fill(path);
      if (index===agent.placements.length-1&&training) {
        context.shadowColor='rgba(113,133,49,.45)';
        context.shadowBlur=9;
      }
      context.strokeStyle = index===agent.placements.length-1 && training ? '#718531' : 'rgba(22,25,21,.72)';
      context.lineWidth = index===agent.placements.length-1 && training ? 2 : .9;
      context.stroke(path);
      if(placement.module.family==='sheared'){
        context.save();context.clip(path);context.strokeStyle='rgba(53,63,45,.2)';context.lineWidth=1;
        const b=G.boundsOf(placement.poly),start=screenPoint({x:b.minX-2,y:b.minY-2}),end=screenPoint({x:b.maxX+2,y:b.maxY+2});
        for(let x=start.x-(end.y-start.y);x<end.x;x+=7){context.beginPath();context.moveTo(x,start.y);context.lineTo(x+(end.y-start.y),end.y);context.stroke();}
        context.restore();
      }
      if(placement.module.category==='corridor'){
        const c=screenPoint(placement.center),angle=placement.rotation*Math.PI/180,length=Math.sqrt(placement.module.area)*view.scale*.75;
        context.save();
        context.clip(path);
        context.strokeStyle='rgba(73,60,20,.58)';
        context.lineWidth=1;
        context.setLineDash([4,3]);
        context.beginPath();
        context.moveTo(c.x-Math.cos(angle)*length,c.y-Math.sin(angle)*length);
        context.lineTo(c.x+Math.cos(angle)*length,c.y+Math.sin(angle)*length);
        context.stroke();
        context.setLineDash([]);
        context.restore();
      }
      if (view.scale >= 12 && placement.module.area >= 8) {
        const c = screenPoint(placement.center);
        context.fillStyle = '#161915';
        context.font = `500 ${Math.max(7,Math.min(9,view.scale*.5))}px 'DM Mono', monospace`;
        context.textAlign = 'center';
        context.textBaseline = 'middle';
        context.fillText(placement.module.id,c.x,c.y);
      }
      context.restore();
    });
  }

  function render() {
    if (!agent) return;
    context.clearRect(0,0,cssWidth,cssHeight);
    renderSite();
    renderOrientationBasis();
    context.save();
    context.clip(siteCompoundPath(),'evenodd');
    renderPlacements(performance.now());
    context.restore();
    renderSiteOutline();
  }

  function updateScaleBar() {
    if (!dom.scaleBar) return;
    const options = [1,2,5,10,20,50];
    const metres = options.reduce((best,value) => Math.abs(value*view.scale-110)<Math.abs(best*view.scale-110)?value:best,options[0]);
    const segmentWidth = metres*view.scale/5;
    dom.scaleBar.innerHTML = '';
    for (let i=0;i<5;i+=1) {
      const segment = document.createElement('i');
      segment.className = 'scale-segment';
      segment.style.width = `${segmentWidth}px`;
      if (i===0) {
        const zero = document.createElement('span');
        zero.className = 'scale-tick';
        zero.style.left = '0';
        zero.textContent = '0';
        segment.appendChild(zero);
      }
      const tick = document.createElement('span');
      tick.className = 'scale-tick';
      tick.style.left = '100%';
      tick.textContent = i===4 ? `${metres} m` : String((metres/5)*(i+1));
      segment.appendChild(tick);
      dom.scaleBar.appendChild(segment);
    }
  }

  function updateSparkline() {
    const values = agent.scoreHistory.length ? agent.scoreHistory : [0];
    const points = values.map((value,index) => ({x: values.length===1?0:index/(values.length-1)*260, y:42-(value/100)*38}));
    const line = points.map((p,index) => `${index?'L':'M'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
    const area = `${line} L260,44 L0,44 Z`;
    dom.scoreSparkline.querySelector('.spark-line').setAttribute('d',line);
    dom.scoreSparkline.querySelector('.spark-area').setAttribute('d',area);
  }

  function updateQuality(metrics) {
    const order=['Fill','Circulation','Orientation','Atrium use','Novelty','Shear use','Regularity','Reuse','Daylight','Buildability','Compactness','Travel'];
    dom.qualityBars.innerHTML = '';
    order.forEach((name) => {
      if (name==='Travel' && agent.settings.singleFloor) return;
      const value = metrics.qualities[name] || 0;
      const row = document.createElement('div');
      row.className = 'quality-row';
      row.innerHTML = `<label>${name.toUpperCase()}</label><div class="quality-track"><i style="width:${(value*100).toFixed(1)}%"></i></div><output>${Math.round(value*100)}</output>`;
      dom.qualityBars.appendChild(row);
    });
  }

  function drawModuleCard(canvasElement,module) {
    const ctx = canvasElement.getContext('2d');
    const rect = canvasElement.getBoundingClientRect();
    const dpr = Math.min(2,window.devicePixelRatio||1);
    const w = Math.max(50,Math.round(rect.width||60));
    const h = 42;
    canvasElement.width = w*dpr;
    canvasElement.height = h*dpr;
    ctx.setTransform(dpr,0,0,dpr,0,0);
    const b = G.boundsOf(module.poly);
    const scale = Math.min((w-16)/(b.maxX-b.minX),(h-12)/(b.maxY-b.minY));
    const ox = w/2-(b.minX+b.maxX)/2*scale;
    const oy = h/2-(b.minY+b.maxY)/2*scale;
    ctx.beginPath();
    module.poly.forEach((p,index) => index?ctx.lineTo(p.x*scale+ox,p.y*scale+oy):ctx.moveTo(p.x*scale+ox,p.y*scale+oy));
    ctx.closePath();
    ctx.fillStyle = colors[module.category];
    ctx.strokeStyle = '#555950';
    ctx.lineWidth = 1;
    ctx.fill();ctx.stroke();
  }

  function updateDictionary() {
    dom.dictCount.textContent = `${agent.dictionary.length} / ${agent.settings.dictCap}`;
    dom.moduleDictionary.innerHTML = '';
    agent.dictionary.forEach((module) => {
      const card = document.createElement('div');
      card.className = 'module-card';
      card.setAttribute('aria-label',`${module.id}, ${module.category}, ${module.area} square metres, used ${module.uses} times`);
      const preview = document.createElement('canvas');
      const caption = document.createElement('div');
      caption.innerHTML=`<strong>${module.id}</strong><span>${module.family.toUpperCase()} · ×${module.uses}</span>`;
      card.append(preview,caption);
      dom.moduleDictionary.appendChild(card);
      drawModuleCard(preview,module);
    });
  }

  function updatePolicyWeights() {
    dom.policyWeights.innerHTML = '';
    window.ModularRLAgent.FEATURE_NAMES.forEach((name) => {
      const chip = document.createElement('span');
      chip.className = 'weight-chip';
      chip.innerHTML = `${name.toUpperCase()} <strong>${agent.weights[name]>=0?'+':''}${agent.weights[name].toFixed(2)}</strong>`;
      dom.policyWeights.appendChild(chip);
    });
  }

  function updateUI(force=false) {
    if (!force && renderedEpisode===agent.episode && renderedStep===agent.stepCount) return;
    const metrics = agent.metrics;
    dom.episodeValue.textContent = String(agent.episode).padStart(3,'0');
    dom.stepValue.textContent = String(agent.stepCount).padStart(3,'0');
    dom.canvasEmpty.classList.toggle('hidden',agent.placements.length>0);
    dom.siteAreaCaption.textContent=`NET ${metrics.siteArea.toFixed(0)} m² · ${(agent.boundary.family||agent.boundary.type).toUpperCase()} · ${agent.site.reflexVertices} REFLEX`;
    dom.orientationCaption.textContent=`ORIENTATION BASIS ${agent.episodeOrientation.toFixed(agent.episodeOrientation%1?1:0)}° · ${metrics.spatialNovelty?Math.round(metrics.spatialNovelty*100):0}% NOVELTY`;
    const violations=metrics.boundaryViolations+metrics.overlapViolations;
    dom.geometryAudit.textContent=`EXACT GEOMETRY · ${violations} VIOLATION${violations===1?'':'S'}`;
    dom.geometryAudit.classList.toggle('invalid',violations>0);
    dom.fillMetric.textContent = `${(metrics.fillRatio*100).toFixed(1)}%`;
    dom.fillBar.style.width = `${Math.min(100,metrics.fillRatio*100)}%`;
    dom.areaMetric.textContent = `${metrics.filledArea.toFixed(0)} / ${metrics.siteArea.toFixed(0)} m² placed`;
    dom.moduleMetric.textContent = metrics.moduleCount;
    dom.moduleLimitMetric.textContent = `of ${agent.settings.maxModules} cap`;
    dom.dictMetric.textContent = `${metrics.dictionaryUsed}/${agent.dictionary.length}`;
    dom.reuseMetric.textContent = `${Math.round(metrics.reuse*100)}% reuse`;
    dom.lightMetric.textContent = metrics.filledArea ? `${Math.round(metrics.daylight*100)}%` : '—';
    dom.travelMetric.textContent=agent.settings.singleFloor?'N/A':`${Math.round(metrics.circulationQuality*100)}%`;
    dom.travelLimitMetric.textContent=agent.settings.singleFloor?'single-floor mode':`${metrics.servedRooms}/${agent.placements.filter((placement)=>placement.module.category==='room').length} rooms served`;
    dom.rewardValue.textContent = `${agent.currentReward>=0?'+':''}${agent.currentReward.toFixed(2)}`;
    const displayScore = agent.done ? metrics.score : agent.lastScore || metrics.score;
    dom.scoreValue.textContent = displayScore.toFixed(1);
    const previous = agent.scoreHistory.length>1 ? agent.scoreHistory[agent.scoreHistory.length-2] : 0;
    const delta = agent.lastScore-previous;
    dom.scoreDelta.textContent = agent.scoreHistory.length>1 ? `${delta>=0?'+':''}${delta.toFixed(1)} LAST` : agent.done ? 'FIRST RUN' : 'BASELINE';
    updateQuality(metrics);
    updateDictionary();
    updatePolicyWeights();
    updateSparkline();
    updateScaleBar();
    renderedEpisode = agent.episode;
    renderedStep = agent.stepCount;
  }

  function frame(timestamp) {
    if (training) {
      if (agent.done) {
        if (!nextEpisodeAt) nextEpisodeAt = timestamp+650;
        if (timestamp>=nextEpisodeAt) {
          agent.newEpisode();
          nextEpisodeAt = 0;
          renderedEpisode = -1;
          dom.statusText.textContent = 'Policy learning';
        }
      } else {
        const steps = Math.max(1,Math.ceil(agent.settings.speed/4));
        for (let i=0;i<steps && !agent.done;i+=1) agent.step();
        if (agent.done) {
          dom.statusText.textContent = agent.stalled ? 'Episode complete · frontier closed' : 'Episode complete';
          updateUI(true);
        }
      }
    }
    render();
    updateUI(false);
    requestAnimationFrame(frame);
  }

  function zoomAt(factor,x=cssWidth/2,y=cssHeight/2) {
    const before = {x:(x-view.offsetX)/view.scale,y:(y-view.offsetY)/view.scale};
    view.scale = G.clamp(view.scale*factor,4,60);
    view.offsetX = x-before.x*view.scale;
    view.offsetY = y-before.y*view.scale;
    updateScaleBar();
  }

  function bindEvents() {
    dom.trainBtn.addEventListener('click',() => setTraining(!training));
    dom.newSiteBtn.addEventListener('click',() => rebuildEnvironment(true));
    dom.resetPolicyBtn.addEventListener('click',() => { setTraining(false); agent.updateSettings(settingsFromUI()); agent.resetPolicy(); fitView(); updateUI(true); });
    dom.fitBtn.addEventListener('click',fitView);
    dom.zoomInBtn.addEventListener('click',() => zoomAt(1.2));
    dom.zoomOutBtn.addEventListener('click',() => zoomAt(1/1.2));

    ['minEdge','maxEdge','maxEdges','dictCap','maxModules','travelLimit','learningRate','speed','lobeCount','boundaryVertices','concavity','lobeReach'].forEach((id) => {
      dom[id].addEventListener('input',() => {
        updateControlOutputs();
        agent.updateSettings(settingsFromUI());
        if (['maxModules','travelLimit','learningRate','speed'].includes(id)) {
          renderedStep = -1;
          updateUI(true);
        }
      });
    });
    ['minEdge','maxEdge','maxEdges','dictCap'].forEach((id) => dom[id].addEventListener('change',() => rebuildEnvironment(false)));
    ['lobeCount','boundaryVertices','concavity','lobeReach'].forEach((id)=>dom[id].addEventListener('change',()=>rebuildEnvironment(true)));
    ['boundaryType','atriumPolicy','singleFloor','angleStep','orientationMode','allowShear'].forEach((id) => dom[id].addEventListener('change',() => rebuildEnvironment(id==='boundaryType')));

    canvas.addEventListener('wheel',(event) => {
      event.preventDefault();
      const rect = canvas.getBoundingClientRect();
      zoomAt(event.deltaY<0?1.1:1/1.1,event.clientX-rect.left,event.clientY-rect.top);
    },{passive:false});
    canvas.addEventListener('pointerdown',(event) => {
      canvas.setPointerCapture(event.pointerId);
      drag = {x:event.clientX,y:event.clientY,offsetX:view.offsetX,offsetY:view.offsetY};
      canvas.classList.add('dragging');
    });
    canvas.addEventListener('pointermove',(event) => {
      if (!drag) return;
      view.offsetX = drag.offsetX + event.clientX-drag.x;
      view.offsetY = drag.offsetY + event.clientY-drag.y;
    });
    const stopDrag = () => { drag=null; canvas.classList.remove('dragging'); };
    canvas.addEventListener('pointerup',stopDrag);
    canvas.addEventListener('pointercancel',stopDrag);
    window.addEventListener('keydown',(event) => {
      if (event.code==='Space' && !['INPUT','SELECT','BUTTON'].includes(document.activeElement.tagName)) { event.preventDefault(); setTraining(!training); }
      if (event.key.toLowerCase()==='f') fitView();
    });
    new ResizeObserver(resizeCanvas).observe(stage);
  }

  function initialize() {
    updateControlOutputs();
    agent = new window.ModularRLAgent(settingsFromUI(),Date.now());
    bindEvents();
    resizeCanvas();
    updateUI(true);
    requestAnimationFrame(frame);
  }

  initialize();
})();
