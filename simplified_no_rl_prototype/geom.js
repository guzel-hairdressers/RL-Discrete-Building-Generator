// ============================================================
// MODULAR SPACE FILLING GEOMETRY ENGINE
// ============================================================

var ASTEP = Math.PI/12; // 15 degrees
var PW = 340;
var mainW, mainH, scale, offX, offY;
var boundary = [], holes = [];
var placed = [], frontier = [], dict = [];
var phase = "boundary", seedType = 0, maxAreaM2 = 0, boundaryTimer = 0;
var SHRINK = 0.15;
var debugMsg = "init";

// Slider parameter helpers
function getP(id){return parseFloat(document.getElementById(id).value);}
function maxSides(){return getP("sl-sides");}
function edgeGrid(){return getP("sl-egrid");}
function maxEdge(){return getP("sl-maxe");}
function areaRatio(){return getP("sl-aratio");}
function maxShapes(){return getP("sl-maxsh");}
function nMax(){return getP("sl-nmax");}
function spd(){return getP("sl-spd");}
function snapLen(l){var g=edgeGrid();return Math.max(g,Math.round(l/g)*g);}
function edgeLengths(){var g=edgeGrid(),mx=maxEdge(),a=[];for(var l=g;l<=mx;l+=g)a.push(l);return a;}

// ---- Core Vector Math ----
function pD(a,b){return Math.sqrt((a.x-b.x)*(a.x-b.x)+(a.y-b.y)*(a.y-b.y));}
function pAng(a,b){return Math.atan2(b.y-a.y,b.x-a.x);}
function pCr(a,b){return a.x*b.y-a.y*b.x;}
function pSb(a,b){return{x:a.x-b.x,y:a.y-b.y};}
function rotPt(p,a){var c=Math.cos(a),s=Math.sin(a);return{x:p.x*c-p.y*s,y:p.x*s+p.y*c};}
function toW(lv,tx,ty,r){return lv.map(function(v){var p=rotPt(v,r);return{x:p.x+tx,y:p.y+ty};});}
function cnt(v){var cx=0,cy=0;v.forEach(function(p){cx+=p.x;cy+=p.y;});return{x:cx/v.length,y:cy/v.length};}
function polyAreaM(p){var a=0,n=p.length;for(var i=0;i<n;i++){var j=(i+1)%n;a+=p[i].x*p[j].y-p[j].x*p[i].y;}return Math.abs(a)/2;}
function polyPerimM(p){var r=0,n=p.length;for(var i=0;i<n;i++)r+=pD(p[i],p[(i+1)%n]);return r;}
function m2px(pt){return{x:pt.x*scale+offX,y:pt.y*scale+offY};}

// Point-in-polygon check (Ray-casting)
function pip(pt,poly){
  var x=pt.x,y=pt.y,inside=false,n=poly.length;
  for(var i=0,j=n-1;i<n;j=i++){
    var xi=poly[i].x,yi=poly[i].y,xj=poly[j].x,yj=poly[j].y;
    if(((yi>y)!==(yj>y))&&(x<(xj-xi)*(y-yi)/(yj-yi)+xi)) inside=!inside;
  }
  return inside;
}

// Line segment intersection (with end-point buffer tolerance)
function segsX(a1,a2,b1,b2){
  var d1x=a2.x-a1.x,d1y=a2.y-a1.y,d2x=b2.x-b1.x,d2y=b2.y-b1.y;
  var det=d1x*d2y-d1y*d2x;
  if(Math.abs(det)<1e-10) return false;
  var dx=b1.x-a1.x,dy=b1.y-a1.y;
  var t=(dx*d2y-dy*d2x)/det,u=(dx*d1y-dy*d1x)/det;
  return t>0.02&&t<0.98&&u>0.02&&u<0.98;
}

// Shrink polygon inwards from centroid
function shrinkPoly(poly,amt){
  var c=cnt(poly);
  return poly.map(function(p){
    var dx=p.x-c.x,dy=p.y-c.y,len=Math.sqrt(dx*dx+dy*dy);
    if(len<0.001) return{x:p.x,y:p.y};
    var f=Math.max(0.01,(len-amt))/len;
    return{x:c.x+dx*f,y:c.y+dy*f};
  });
}

// Collision/Overlap check against placed shapes
function overlaps(wv){
  var c1=cnt(wv),r1=0;
  wv.forEach(function(v){r1=Math.max(r1,pD(c1,v));});
  var swv=shrinkPoly(wv,SHRINK);
  for(var pi=0;pi<placed.length;pi++){
    var ov=placed[pi].wv,c2=cnt(ov),r2=0;
    ov.forEach(function(v){r2=Math.max(r2,pD(c2,v));});
    if(pD(c1,c2)>r1+r2+0.3) continue;
    for(var i=0;i<swv.length;i++) if(pip(swv[i],ov)) return true;
    var sov=shrinkPoly(ov,SHRINK);
    for(var i=0;i<sov.length;i++) if(pip(sov[i],wv)) return true;
    var n1=wv.length,n2=ov.length;
    for(var i=0;i<n1;i++) for(var j=0;j<n2;j++)
      if(segsX(wv[i],wv[(i+1)%n1],ov[j],ov[(j+1)%n2])) return true;
  }
  return false;
}

// Boundary check (incorporates 5mm tolerance for float safety)
function insideBoundary(wv){
  var expB = shrinkPoly(boundary, -0.005);
  for(var i=0;i<wv.length;i++) if(!pip(wv[i],expB)) return false;
  // Edge-boundary intersection (catches non-convex crossing)
  for(var i=0;i<wv.length;i++){
    var a=wv[i],b=wv[(i+1)%wv.length];
    for(var j=0;j<expB.length;j++)
      if(segsX(a,b,expB[j],expB[(j+1)%expB.length])) return false;
  }
  var c=cnt(wv);
  for(var h=0;h<holes.length;h++){
    var expH = shrinkPoly(holes[h], -0.005);
    if(pip(c,expH)) return false;
    for(var vi=0;vi<wv.length;vi++) if(pip(wv[vi],expH)) return false;
    // Check if any hole vertices are inside the shape (engulfment prevention)
    for(var vi=0;vi<expH.length;vi++) if(pip(expH[vi],wv)) return false;
    for(var i=0;i<wv.length;i++){
      var a=wv[i],b=wv[(i+1)%wv.length];
      for(var j=0;j<expH.length;j++)
        if(segsX(a,b,expH[j],expH[(j+1)%expH.length])) return false;
    }
  }
  return true;
}

// Checks if an edge is shared by >=2 placed shapes (so it is capped)
function edgeClaimed(a,b){
  var count=0,E=0.15;
  for(var pi=0;pi<placed.length;pi++){
    var v=placed[pi].wv,n=v.length;
    for(var i=0;i<n;i++){
      var p=v[i],q=v[(i+1)%n];
      if((pD(a,p)<E&&pD(b,q)<E)||(pD(a,q)<E&&pD(b,p)<E)){count++;break;}
    }
    if(count>=2) return true;
  }
  return false;
}

// Rotation-Invariant signature matching logic
function getSig(lv){
  var n=lv.length;
  var lens=[];
  for(var i=0;i<n;i++) lens.push(Math.round(pD(lv[i],lv[(i+1)%n])*10)/10);
  var angs=[];
  for(var i=0;i<n;i++){
    var prev=lv[(i-1+n)%n],cur=lv[i],next=lv[(i+1)%n];
    var a1=Math.atan2(prev.y-cur.y,prev.x-cur.x);
    var a2=Math.atan2(next.y-cur.y,next.x-cur.x);
    var ia=((a2-a1)%(Math.PI*2)+Math.PI*2)%(Math.PI*2);
    angs.push(Math.round(ia/ASTEP));
  }
  var best=null;
  for(var fwd=0;fwd<2;fwd++){
    var L=fwd?lens.slice():lens.slice().reverse();
    var A;
    if(fwd){
      A=angs.slice();
    }else{
      A=angs.slice().reverse().map(function(a){return(24-a)%24;});
    }
    for(var s=0;s<n;s++){
      var rL=L.slice(s).concat(L.slice(0,s));
      var rA=A.slice(s).concat(A.slice(0,s));
      var seq="";
      for(var i=0;i<n;i++) seq+=Math.round(rL[i]*100)+","+rA[i]+"|";
      if(best===null||seq<best) best=seq;
    }
  }
  return n+":"+best;
}

// Simple non-intersecting polygon check
function isSimple(verts){
  var n=verts.length;
  for(var i=0;i<n;i++){
    for(var j=i+2;j<n;j++){
      if(i===0&&j===n-1) continue;
      if(segsX(verts[i],verts[(i+1)%n],verts[j],verts[(j+1)%n])) return false;
    }
  }
  return true;
}

// Deepest interior point search inside poly (for spawning holes safely)
function findInteriorPointOf(pts) {
  var xs=pts.map(function(p){return p.x;}),ys=pts.map(function(p){return p.y;});
  var xMin=Math.min.apply(null,xs),xMax=Math.max.apply(null,xs);
  var yMin=Math.min.apply(null,ys),yMax=Math.max.apply(null,ys);
  var best=null,bestDist=0,G=25;
  for(var gx=0;gx<G;gx++) for(var gy=0;gy<G;gy++){
    var pt={x:xMin+(xMax-xMin)*(gx+0.5)/G,y:yMin+(yMax-yMin)*(gy+0.5)/G};
    if(!pip(pt,pts)) continue;
    var md=1e9;
    for(var i=0;i<pts.length;i++){
      var a=pts[i],b=pts[(i+1)%pts.length];
      var dx=b.x-a.x,dy=b.y-a.y,l2=dx*dx+dy*dy;
      if(l2<0.001) continue;
      var t=Math.max(0,Math.min(1,((pt.x-a.x)*dx+(pt.y-a.y)*dy)/l2));
      md=Math.min(md,pD(pt,{x:a.x+t*dx,y:a.y+t*dy}));
    }
    if(md>bestDist){bestDist=md;best=pt;}
  }
  return {pt: best || cnt(pts), dist: bestDist};
}

// Deepest interior point search inside boundary (for seed placing)
function findInteriorPoint(){
  var xs=boundary.map(function(p){return p.x;}),ys=boundary.map(function(p){return p.y;});
  var xMin=Math.min.apply(null,xs),xMax=Math.max.apply(null,xs);
  var yMin=Math.min.apply(null,ys),yMax=Math.max.apply(null,ys);
  var best=null,bestDist=0,G=30;
  for(var gx=0;gx<G;gx++) for(var gy=0;gy<G;gy++){
    var pt={x:xMin+(xMax-xMin)*(gx+0.5)/G,y:yMin+(yMax-yMin)*(gy+0.5)/G};
    if(!pip(pt,boundary)) continue;
    var inH=false;for(var h=0;h<holes.length;h++) if(pip(pt,holes[h])) inH=true;
    if(inH) continue;
    var md=1e9;
    for(var i=0;i<boundary.length;i++){
      var a=boundary[i],b=boundary[(i+1)%boundary.length];
      var dx=b.x-a.x,dy=b.y-a.y,l2=dx*dx+dy*dy;
      if(l2<0.001) continue;
      var t=Math.max(0,Math.min(1,((pt.x-a.x)*dx+(pt.y-a.y)*dy)/l2));
      md=Math.min(md,pD(pt,{x:a.x+t*dx,y:a.y+t*dy}));
    }
    if(md>bestDist){bestDist=md;best=pt;}
  }
  return best||cnt(boundary);
}

// ---- boundaries ----
function makeBoundary(type){
  var t=type%8,pts=[],h=[];
  if(t===0){
    // FREE boundary: arbitrary star-convex polygon with random radius variations
    var n = 8 + Math.floor(Math.random()*6); // 8 to 13 sides
    var angles = [];
    for(var i=0; i<n; i++) angles.push(Math.random()*Math.PI*2);
    angles.sort(function(a,b){return a-b;});
    
    for(var i=0; i<n; i++) {
      var a = angles[i];
      var r = 10 + Math.random()*12; // 10 to 22 meters
      // Indent 3 of the vertices deeply to make it non-convex
      if(i === 2 || i === Math.floor(n/2) || i === n-2) {
        if(Math.random() < 0.7) r = 4 + Math.random()*3;
      }
      pts.push({x: Math.cos(a)*r, y: Math.sin(a)*r});
    }
  }
  else if(t===1){var w=16+Math.random()*18,d=8+Math.random()*5;pts=[{x:-w/2,y:-d/2},{x:w/2,y:-d/2},{x:w/2,y:d/2},{x:-w/2,y:d/2}];}
  else if(t===2){var w=18+Math.random()*10,d=16+Math.random()*6,cw=w*0.45,cd=d*0.45;pts=[{x:-w/2,y:-d/2},{x:w/2,y:-d/2},{x:w/2,y:-d/2+cd},{x:-w/2+cw,y:-d/2+cd},{x:-w/2+cw,y:d/2},{x:-w/2,y:d/2}];}
  else if(t===3){var w=22+Math.random()*8,d=18+Math.random()*6,arm=4+Math.random()*3,gap=w*0.4;pts=[{x:-w/2,y:-d/2},{x:w/2,y:-d/2},{x:w/2,y:d/2},{x:gap/2,y:d/2},{x:gap/2,y:-d/2+arm},{x:-gap/2,y:-d/2+arm},{x:-gap/2,y:d/2},{x:-w/2,y:d/2}];}
  else if(t===4){var w=35+Math.random()*15,d=5+Math.random()*4;pts=[{x:-w/2,y:-d/2},{x:w/2,y:-d/2},{x:w/2,y:d/2},{x:-w/2,y:d/2}];}
  else if(t===5){var n=6+Math.floor(Math.random()*3),r=8+Math.random()*5;for(var i=0;i<n;i++){var a=(i/n)*Math.PI*2-Math.PI/2;var sa=Math.round(a/ASTEP)*ASTEP;pts.push({x:Math.cos(sa)*r*(0.88+Math.random()*0.12),y:Math.sin(sa)*r*(0.88+Math.random()*0.12)});}}
  else if(t===6){var bw=24+Math.random()*8,bh=5+Math.random()*3,sw=7+Math.random()*3,sh=12+Math.random()*4;pts=[{x:-bw/2,y:-bh/2},{x:bw/2,y:-bh/2},{x:bw/2,y:bh/2},{x:sw/2,y:bh/2},{x:sw/2,y:bh/2+sh},{x:-sw/2,y:bh/2+sh},{x:-sw/2,y:bh/2},{x:-bw/2,y:bh/2}];}
  else{var top=7+Math.random()*5,bot=16+Math.random()*8,hh=10+Math.random()*6;pts=[{x:-top/2,y:-hh/2},{x:top/2,y:-hh/2},{x:bot/2,y:hh/2},{x:-bot/2,y:hh/2}];}
  
  // Safe hole spawning: find the point deepest inside the boundary
  if(polyAreaM(pts)>160 && Math.random()<0.35){
    var res = findInteriorPointOf(pts);
    var c = res.pt;
    var d = res.dist;
    if (d > 3.0) { // Only spawn hole if we have at least a 3m radius corridor
      var hr = Math.min(d - 1.5, Math.max(1.2, d * 0.35 + Math.random()*0.5));
      var hn = 4 + Math.floor(Math.random()*3), hole = [];
      for(var i=0;i<hn;i++){
        var a=(i/hn)*Math.PI*2;
        hole.push({
          x: c.x + Math.cos(a)*hr*(0.9 + Math.random()*0.15),
          y: c.y + Math.sin(a)*hr*(0.9 + Math.random()*0.15)
        });
      }
      h.push(hole);
    }
  }
  return{pts:pts,holes:h};
}

// Recalculates canvas viewing scale and centering translations
function computeScale(){
  var xs=boundary.map(function(p){return p.x;}),ys=boundary.map(function(p){return p.y;});
  var xMin=Math.min.apply(null,xs),xMax=Math.max.apply(null,xs);
  var yMin=Math.min.apply(null,ys),yMax=Math.max.apply(null,ys);
  var bw=xMax-xMin,bh=yMax-yMin,margin=80;
  scale=Math.min((mainW-2*margin)/bw,(mainH-2*margin)/bh);
  offX=mainW/2-(xMin+xMax)/2*scale;
  offY=mainH/2-(yMin+yMax)/2*scale;
}
