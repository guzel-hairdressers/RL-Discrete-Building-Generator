// ============================================================
// MODULAR SPACE FILLING PROCESSOR (p5.js Sketch)
// ============================================================

var FILLS = [
  "#f0f0f0","#e8edf2","#f2ece6","#e6f0e8","#f0e8f0",
  "#eef2e6","#e6eef2","#f2e6ea","#eaf2e6","#f0eee6",
  "#e8e6f2","#f2f0e6","#e6f2ee","#f0e6e8","#e6e8f2",
  "#f0f2e6","#ece6f2","#e6f2e6","#f2e8e6","#e6f0f2"
];

function setup(){
  var c=createCanvas(windowWidth-PW,windowHeight);
  c.parent(document.body);c.elt.classList.add('p5Canvas');
  mainW=width;mainH=height;
  setupControls();
  initDemo();
}

function setupControls(){
  var names=["Free","Rect","L-shape","U-shape","Bar","Hex","T-shape","Trapezoid"];
  var div=document.getElementById("bnd-btns");
  names.forEach(function(n,i){
    var b=document.createElement("button");b.className="btn";b.textContent=n;
    b.onclick=function(){seedType=i;initDemo();};div.appendChild(b);
  });
  ["sides","egrid","maxe","aratio","maxsh","nmax","spd"].forEach(function(k){
    var sl=document.getElementById("sl-"+k),vl=document.getElementById("v-"+k);
    sl.oninput=function(){
      var v=parseFloat(sl.value);
      vl.textContent=(k==="aratio"||k==="egrid")?v.toFixed(k==="aratio"?2:1):v;
    };
  });
}

// Keyboard shortcuts
function keyPressed() {
  if (key === ' ' || keyCode === 32) {
    nextBoundary();
  } else if (key === 'r' || key === 'R') {
    initDemo();
  }
}

// Mouse panning & dragging support
var isDragging = false;
var startX, startY;
function mousePressed() {
  if (mouseX > 0 && mouseX < mainW && mouseY > 0 && mouseY < mainH) {
    isDragging = true;
    startX = mouseX - offX;
    startY = mouseY - offY;
  }
}
function mouseDragged() {
  if (isDragging) {
    offX = mouseX - startX;
    offY = mouseY - startY;
  }
}
function mouseReleased() {
  isDragging = false;
}
function mouseWheel(event) {
  if (mouseX > 0 && mouseX < mainW && mouseY > 0 && mouseY < mainH) {
    var zoomFactor = event.delta < 0 ? 1.05 : 0.95;
    var mx = mouseX, my = mouseY;
    var wx = (mx - offX) / scale;
    var wy = (my - offY) / scale;
    scale *= zoomFactor;
    offX = mx - wx * scale;
    offY = my - wy * scale;
    return false; // prevent page scroll
  }
}

// ---- init ----
function initDemo(){
  placed=[];frontier=[];dict=[];maxAreaM2=0;
  phase="boundary";boundaryTimer=0;
  var b=makeBoundary(seedType);boundary=b.pts;holes=b.holes;
  computeScale();updateDictUI();
}
function nextBoundary(){seedType++;initDemo();}

// ---- strict geometry generator ----
function generateStrictShapes(fp0, fp1, pc) {
  var eDir = pAng(fp0, fp1);
  var L0 = pD(fp0, fp1);
  var pSide = pCr(pSb(fp1, fp0), pSb(pc, fp0));
  var EL = edgeLengths();
  var shapes = [];

  function addShape(vecs) {
    var wv = [ {x:fp0.x, y:fp0.y} ];
    var cur = {x:fp0.x, y:fp0.y};
    for(var i=0; i<vecs.length-1; i++) {
      cur = {x: cur.x + Math.cos(eDir + vecs[i].ang)*vecs[i].len, 
             y: cur.y + Math.sin(eDir + vecs[i].ang)*vecs[i].len};
      wv.push(cur);
    }
    var vc = cnt(wv);
    if (pSide * pCr(pSb(fp1,fp0), pSb(vc,fp0)) >= 0) return;
    if (!isSimple(wv)) return;
    shapes.push(wv);
  }

  // 1) Parallelograms (includes rectangles). Internal angles constrained to >=45°
  for(var i=0; i<EL.length; i++) {
    var L1 = EL[i];
    for(var k=3; k<=9; k++) { 
      var ang = k * ASTEP;
      addShape([{len:L0,ang:0},{len:L1,ang:ang},{len:L0,ang:Math.PI},{len:L1,ang:Math.PI+ang}]);
      addShape([{len:L0,ang:0},{len:L1,ang:-ang},{len:L0,ang:Math.PI},{len:L1,ang:Math.PI-ang}]);
    }
  }

  // 2) Equilateral Triangles
  if (maxSides() >= 3) {
    addShape([{len:L0,ang:0},{len:L0,ang:Math.PI*2/3},{len:L0,ang:Math.PI*4/3}]);
    addShape([{len:L0,ang:0},{len:L0,ang:-Math.PI*2/3},{len:L0,ang:-Math.PI*4/3}]);
  }

  // 3) 60-degree Trapezoids
  if (maxSides() >= 4) {
    for(var i=0; i<EL.length; i++) {
      var L1 = EL[i];
      var topL = L0 + L1;
      if (topL <= maxEdge() + 0.05) {
        addShape([{len:L0,ang:0},{len:L1,ang:Math.PI/3},{len:topL,ang:Math.PI},{len:L1,ang:Math.PI*5/3}]);
        addShape([{len:L0,ang:0},{len:L1,ang:-Math.PI/3},{len:topL,ang:Math.PI},{len:L1,ang:-Math.PI*5/3}]);
      }
      var topL2 = L0 - L1;
      if (topL2 >= edgeGrid() - 0.05) {
        addShape([{len:L0,ang:0},{len:L1,ang:Math.PI*2/3},{len:topL2,ang:Math.PI},{len:L1,ang:Math.PI*4/3}]);
        addShape([{len:L0,ang:0},{len:L1,ang:-Math.PI*2/3},{len:topL2,ang:Math.PI},{len:L1,ang:-Math.PI*4/3}]);
      }
    }
  }

  // 4) Zonogon Hexagons
  if (maxSides() >= 6) {
    for(var i=0; i<EL.length; i+=2) {
      var L1 = EL[i];
      for(var j=0; j<EL.length; j+=2) {
        var L2 = EL[j];
        var pairs = [[30,90], [45,90], [60,120], [30,150], [45,135], [90,150]];
        for(var a=0; a<pairs.length; a++) {
          var a1 = pairs[a][0]*Math.PI/180, a2 = pairs[a][1]*Math.PI/180;
          addShape([{len:L0,ang:0},{len:L1,ang:a1},{len:L2,ang:a2},{len:L0,ang:Math.PI},{len:L1,ang:Math.PI+a1},{len:L2,ang:Math.PI+a2}]);
          addShape([{len:L0,ang:0},{len:L1,ang:-a1},{len:L2,ang:-a2},{len:L0,ang:Math.PI},{len:L1,ang:Math.PI-a1},{len:L2,ang:Math.PI-a2}]);
        }
      }
    }
  }

  // 5) Zonogon Octagons
  if (maxSides() >= 8) {
    var L1 = edgeGrid(), L2 = edgeGrid(), L3 = edgeGrid();
    var a1 = 45*Math.PI/180, a2 = 90*Math.PI/180, a3 = 135*Math.PI/180;
    addShape([
      {len:L0,ang:0},{len:L1,ang:a1},{len:L2,ang:a2},{len:L3,ang:a3},
      {len:L0,ang:Math.PI},{len:L1,ang:Math.PI+a1},{len:L2,ang:Math.PI+a2},{len:L3,ang:Math.PI+a3}
    ]);
    addShape([
      {len:L0,ang:0},{len:L1,ang:-a1},{len:L2,ang:-a2},{len:L3,ang:-a3},
      {len:L0,ang:Math.PI},{len:L1,ang:Math.PI-a1},{len:L2,ang:Math.PI-a2},{len:L3,ang:Math.PI-a3}
    ]);
  }

  return shapes;
}

function startGrowth(){
  phase="growing";
  var c=findInteriorPoint();
  var EL=edgeLengths();
  var shapes = [];
  for (var i=0; i<EL.length; i++) {
    var L0 = EL[i];
    var fp0 = {x: -L0/2, y: 0}, fp1 = {x: L0/2, y: 0}, pc = {x: 0, y: 1};
    shapes = shapes.concat(generateStrictShapes(fp0, fp1, pc));
  }
  debugMsg = "sh:" + shapes.length;
  
  for(var i=shapes.length-1; i>0; i--) {
    var j=Math.floor(Math.random()*(i+1));
    var t=shapes[i]; shapes[i]=shapes[j]; shapes[j]=t;
  }
  
  for(var i=0; i<shapes.length; i++) {
    var lv = shapes[i];
    var rot = Math.floor(Math.random()*24)*ASTEP;
    var lvRot = lv.map(function(v){return rotPt(v, rot);});
    var wv = lvRot.map(function(v){return {x: v.x+c.x, y: v.y+c.y};});
    if (insideBoundary(wv) && !overlaps(wv)) {
      var idx = lookupOrAdd(lvRot);
      if (idx < 0) idx = 0;
      maxAreaM2 = polyAreaM(lvRot);
      placed.push({wv:wv, dictIdx:idx, born:frameCount});
      var cc=cnt(wv), n=wv.length;
      for(var j=0; j<n; j++) frontier.push({p0:wv[j], p1:wv[(j+1)%n], pc:cc, retries:0});
      return;
    }
  }
  phase="done";
}

function lookupOrAdd(lv){
  var sig=getSig(lv);
  for(var i=0;i<dict.length;i++) if(dict[i].sig===sig){dict[i].count++;return i;}
  if(dict.length<nMax()){
    var idx=dict.length;
    dict.push({lv:lv,sig:sig,count:1});
    return idx;
  }
  return -1;
}

function tryDictShape(dIdx,fp0,fp1,pc){
  var lv=dict[dIdx].lv,n=lv.length,tLen=pD(fp0,fp1);
  var pSide=pCr(pSb(fp1,fp0),pSb(pc,fp0));
  var TOL=0.05;

  for(var ei=0;ei<n;ei++){
    var ea=lv[ei],eb=lv[(ei+1)%n];
    if(Math.abs(pD(ea,eb)-tLen)>TOL) continue;
    var tries=[
      {tA:pAng(fp0,fp1),anc:fp0,lp:ea,ln:eb},
      {tA:pAng(fp1,fp0),anc:fp1,lp:eb,ln:ea}
    ];
    for(var ti=0;ti<tries.length;ti++){
      var tr=tries[ti],r=tr.tA-pAng(tr.lp,tr.ln);
      var ra=rotPt(tr.lp,r);
      var wv=toW(lv,tr.anc.x-ra.x,tr.anc.y-ra.y,r);
      var vc=cnt(wv);
      if(pSide*pCr(pSb(fp1,fp0),pSb(vc,fp0))>=0) continue;
      var area=polyAreaM(wv);
      if(maxAreaM2>0&&area<maxAreaM2*areaRatio()) continue;
      if(insideBoundary(wv)&&!overlaps(wv)) return wv;
    }
  }
  return null;
}

function createShape(fp0, fp1, pc) {
  var shapes = generateStrictShapes(fp0, fp1, pc);
  for(var i=shapes.length-1; i>0; i--) {
    var j=Math.floor(Math.random()*(i+1));
    var t=shapes[i]; shapes[i]=shapes[j]; shapes[j]=t;
  }
  var g = edgeGrid();
  for(var i=0; i<shapes.length; i++) {
    var poly = shapes[i];
    var area = polyAreaM(poly);
    if (area < g*g*0.3) continue;
    if (maxAreaM2 > 0 && area < maxAreaM2*areaRatio()) continue;
    if (insideBoundary(poly) && !overlaps(poly)) return poly;
  }
  return null;
}

function commit(wv,dIdx,fp0,fp1){
  var area=polyAreaM(wv);if(area>maxAreaM2) maxAreaM2=area;
  placed.push({wv:wv,dictIdx:dIdx,born:frameCount});
  var vc=cnt(wv),n=wv.length;
  for(var i=0;i<n;i++){
    var a=wv[i],b=wv[(i+1)%n];
    if((pD(a,fp1)<0.15&&pD(b,fp0)<0.15)||(pD(a,fp0)<0.15&&pD(b,fp1)<0.15)) continue;
    if(!edgeClaimed(a,b)) frontier.push({p0:a,p1:b,pc:vc,retries:0});
  }
}

function growStep(){
  if(frontier.length===0||placed.length>=maxShapes()){phase="done";return;}
  var ei=Math.floor(Math.random()*Math.min(frontier.length,50));
  var edge=frontier[ei];
  if(edgeClaimed(edge.p0,edge.p1)){frontier.splice(ei,1);return;}

  // 1) Try rigid fit from dictionary
  var shuff=Array.from({length:dict.length},function(_,i){return i;});
  for(var i=shuff.length-1;i>0;i--){var j=Math.floor(Math.random()*(i+1));var t=shuff[i];shuff[i]=shuff[j];shuff[j]=t;}
  for(var i=0;i<shuff.length;i++){
    var dIdx=shuff[i];
    var wv=tryDictShape(dIdx,edge.p0,edge.p1,edge.pc);
    if(wv){
      frontier.splice(ei,1);
      commit(wv,dIdx,edge.p0,edge.p1);
      return;
    }
  }

  // 2) Create new if dict not full
  if(dict.length<nMax()){
    var wv=createShape(edge.p0,edge.p1,edge.pc);
    if(wv){
      frontier.splice(ei,1);
      var vc=cnt(wv);var lv=wv.map(function(v){return{x:v.x-vc.x,y:v.y-vc.y};});
      var idx=lookupOrAdd(lv);
      if(idx>=0) commit(wv,idx,edge.p0,edge.p1);
      return;
    }
  }

  // 3) Failed: retry up to 20 times before discarding
  edge.retries=(edge.retries||0)+1;
  if(edge.retries>20) frontier.splice(ei,1);
}

// ---- Graphic Scale bar & HUD Helpers ----
function getScaleDiv() {
  var divs = [0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0];
  var targetPx = mainW * 0.25;
  var targetD = targetPx / (10 * scale);
  var best = divs[0], bestDiff = Math.abs(divs[0] - targetD);
  for (var i = 1; i < divs.length; i++) {
    var diff = Math.abs(divs[i] - targetD);
    if (diff < bestDiff) {
      bestDiff = diff;
      best = divs[i];
    }
  }
  return best;
}

function drawGraphPaper() {
  push();
  strokeWeight(0.5);
  for (var x = 0; x < width; x += 10) {
    if (x % 50 === 0) stroke(230);
    else stroke(244);
    line(x, 0, x, height);
  }
  for (var y = 0; y < height; y += 10) {
    if (y % 50 === 0) stroke(230);
    else stroke(244);
    line(0, y, width, y);
  }
  pop();
}

function drawTitleBlock() {
  push();
  noStroke();
  var tx = 25, ty = 25;
  
  fill(0);
  textFont('Space Grotesk');
  textStyle(BOLD);
  textSize(14);
  textAlign(LEFT, TOP);
  text("Modular Space Filling Prototype", tx, ty);
  
  var bArea = polyAreaM(boundary);
  var filledArea = 0, areas = [];
  for (var i = 0; i < placed.length; i++) {
    var a = polyAreaM(placed[i].wv);
    filledArea += a;
    areas.push(a);
  }
  var far = bArea > 0 ? filledArea / bArea : 0;
  var minA = areas.length ? Math.min.apply(null, areas) : 0;
  var maxA = areas.length ? Math.max.apply(null, areas) : 0;
  var ratio = maxA > 0 ? (minA / maxA).toFixed(2) : "—";
  var tri = 0, quad = 0;
  placed.forEach(function(p) { p.wv.length <= 3 ? tri++ : quad++; });
  
  fill(80);
  textFont('Space Mono');
  textStyle(NORMAL);
  textSize(8.5);
  textAlign(LEFT, TOP);
  
  var line1 = "BOUNDARY: " + bArea.toFixed(1) + " m²  |  FILLED: " + filledArea.toFixed(1) + " m² (" + Math.round(far * 100) + "%)";
  var line2 = "MODULES:  " + placed.length + " (" + quad + " quads+, " + tri + " tri)";
  var line3 = "AREA MIN/MAX: " + minA.toFixed(1) + " / " + maxA.toFixed(1) + " m² (Ratio: " + ratio + ")";
  
  text(line1, tx, ty + 20);
  text(line2, tx, ty + 32);
  text(line3, tx, ty + 44);
  pop();
}

function draw(){
  background(255);
  drawGraphPaper();

  if(phase==="boundary"){boundaryTimer++;if(boundaryTimer>60) startGrowth();}
  if(phase==="growing"){
    var s=spd();
    for(var i=0;i<s;i++) if(frontier.length>0&&placed.length<maxShapes()&&phase==="growing") growStep();
  }

  // Placed shapes (solid white fill, clean black outline)
  for(var i=0; i<placed.length; i++){
    var r=placed[i];
    fill(255);stroke(40);strokeWeight(1.2);
    beginShape();r.wv.forEach(function(v){var sp=m2px(v);vertex(sp.x,sp.y);});endShape(CLOSE);
  }

  // Labels (centered, clean)
  noStroke();fill(80);textSize(8);textAlign(CENTER, CENTER);
  for(var i=0; i<placed.length; i++){
    var r=placed[i],vc=cnt(r.wv),sp=m2px(vc);
    text("M"+(r.dictIdx+1), sp.x, sp.y);
  }

  // Holes
  for(var hi=0;hi<holes.length;hi++){
    noFill();stroke(40);strokeWeight(1.5);
    beginShape();holes[hi].forEach(function(p){var sp=m2px(p);vertex(sp.x,sp.y);});endShape(CLOSE);
  }

  // Boundary ON TOP
  noFill();stroke(20);strokeWeight(2.5);
  beginShape();boundary.forEach(function(p){var sp=m2px(p);vertex(sp.x,sp.y);});endShape(CLOSE);
  for(var hi=0;hi<holes.length;hi++){
    noFill();stroke(40);strokeWeight(2);
    beginShape();holes[hi].forEach(function(p){var sp=m2px(p);vertex(sp.x,sp.y);});endShape(CLOSE);
  }

  // Graphic Scale Bar (Staggered style)
  var D = getScaleDiv();
  var p0 = 0;
  var p1 = D * scale;
  var p2 = 2 * D * scale;
  var p3 = 5 * D * scale;
  var p4 = 10 * D * scale;

  var bx = 25; // Margin from left
  var by = mainH - 25; // Position from bottom
  var H = 4;

  noStroke();
  fill(0);
  rect(bx + p0, by - H, p1 - p0, H);
  rect(bx + p1, by, p2 - p1, H);
  rect(bx + p2, by - H, p3 - p2, H);
  rect(bx + p3, by, p4 - p3, H);

  // Labels
  fill(40);
  textSize(8);
  textAlign(CENTER, TOP);
  
  function formatD(val) {
    if (val === 0) return "0";
    return val >= 1 ? val.toFixed(0) + "m" : val.toFixed(1) + "m";
  }

  text(formatD(0), bx + p0, by + H + 4);
  text(formatD(D), bx + p1, by + H + 4);
  text(formatD(2 * D), bx + p2, by + H + 4);
  text(formatD(5 * D), bx + p3, by + H + 4);
  text(formatD(10 * D), bx + p4, by + H + 4);

  // Draw Title Block on top
  drawTitleBlock();

  // HUD
  var done=phase==="done",bnd=phase==="boundary";
  noStroke();fill(done?245:bnd?245:255);stroke(0);strokeWeight(1);
  var st=done?"DONE ("+placed.length+")":bnd?"BOUNDARY":"GROW "+frontier.length;
  st += " | " + debugMsg;
  textSize(8.5);textAlign(LEFT, CENTER);
  var hx = width - 170;
  var hy = 25;
  rect(hx, hy, 140, 20, 2);
  noStroke();fill(0);text(st, hx + 10, hy + 10);

  if(frameCount%12===0){updateDictUI();updateStats();}
}

// ---- sidebar updates ----
function updateDictUI(){
  var info=document.getElementById("dict-info");if(!info)return;
  info.textContent=dict.length+"/"+nMax()+" types | "+placed.length+" placed";
  var grid=document.getElementById("dict-grid");grid.innerHTML="";
  for(var i=0;i<dict.length;i++){
    var cell=document.createElement("div");cell.className="dict-cell";
    var cv=document.createElement("canvas");
    cv.width=80;cv.height=80;
    cv.style.cssText="display:block!important;position:static!important;width:80px;height:80px;margin:0 auto 2px!important;";
    var ctx=cv.getContext("2d");
    var lv=dict[i].lv,sc=cnt(lv),maxR=0;
    lv.forEach(function(v){maxR=Math.max(maxR,pD(sc,v));});
    var s=30/(maxR||1);
    ctx.fillStyle="#ffffff"; // Solid white fill
    ctx.strokeStyle="#444";ctx.lineWidth=1.5;
    ctx.beginPath();
    lv.forEach(function(v,idx){var x=40+(v.x-sc.x)*s,y=40+(v.y-sc.y)*s;idx===0?ctx.moveTo(x,y):ctx.lineTo(x,y);});
    ctx.closePath();ctx.fill();ctx.stroke();
    cell.appendChild(cv);
    var uses=0;placed.forEach(function(p){if(p.dictIdx===i)uses++;});
    var label=document.createElement("div");
    label.innerHTML="<b>M"+(i+1)+"</b> "+lv.length+"s "+polyAreaM(lv).toFixed(1)+"m\u00B2<br>\u00D7"+uses+" placed";
    cell.appendChild(label);
    grid.appendChild(cell);
  }
}

// Stub function to maintain compatibility (Stats are now drawn on canvas HUD)
function updateStats(){}
