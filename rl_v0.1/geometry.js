(function (global) {
  'use strict';

  const TAU = Math.PI * 2;
  const EPSILON = 1e-7;
  const key = (x, y) => `${x},${y}`;
  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

  class RNG {
    constructor(seed) { this.state = (seed || Date.now()) >>> 0; }
    next() {
      this.state += 0x6D2B79F5;
      let t = this.state;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    }
    int(min, max) { return Math.floor(this.next() * (max - min + 1)) + min; }
    pick(items) { return items[Math.floor(this.next() * items.length)]; }
    shuffle(items) {
      for (let i = items.length - 1; i > 0; i -= 1) {
        const j = this.int(0, i);
        [items[i], items[j]] = [items[j], items[i]];
      }
      return items;
    }
  }

  function polygonArea(poly) {
    let sum = 0;
    for (let i = 0; i < poly.length; i += 1) {
      const a = poly[i];
      const b = poly[(i + 1) % poly.length];
      sum += a.x * b.y - b.x * a.y;
    }
    return Math.abs(sum) / 2;
  }

  function polygonSignedArea(poly){
    let sum=0;
    for(let i=0;i<poly.length;i+=1){const a=poly[i],b=poly[(i+1)%poly.length];sum+=a.x*b.y-b.x*a.y;}
    return sum/2;
  }

  function reflexVertexCount(poly){
    const sign=Math.sign(polygonSignedArea(poly))||1;
    let count=0;
    for(let i=0;i<poly.length;i+=1){
      const previous=poly[(i-1+poly.length)%poly.length],point=poly[i],next=poly[(i+1)%poly.length];
      if(sign*orientation(previous,point,next)<-EPSILON)count+=1;
    }
    return count;
  }

  function polygonPerimeter(poly) {
    let sum = 0;
    for (let i = 0; i < poly.length; i += 1) {
      const a = poly[i];
      const b = poly[(i + 1) % poly.length];
      sum += Math.hypot(b.x - a.x, b.y - a.y);
    }
    return sum;
  }

  function polygonCentroid(poly) {
    let x = 0;
    let y = 0;
    poly.forEach((p) => { x += p.x; y += p.y; });
    return { x: x / poly.length, y: y / poly.length };
  }

  function pointInPolygon(point, poly) {
    let inside = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i, i += 1) {
      const a = poly[i];
      const b = poly[j];
      const crosses = ((a.y > point.y) !== (b.y > point.y)) &&
        (point.x < ((b.x - a.x) * (point.y - a.y)) / ((b.y - a.y) || 1e-9) + a.x);
      if (crosses) inside = !inside;
    }
    return inside;
  }

  function pointOnSegment(point, a, b, epsilon = EPSILON) {
    const cross = (point.x-a.x)*(b.y-a.y)-(point.y-a.y)*(b.x-a.x);
    if (Math.abs(cross) > epsilon) return false;
    const dot = (point.x-a.x)*(b.x-a.x)+(point.y-a.y)*(b.y-a.y);
    if (dot < -epsilon) return false;
    const lengthSquared = (b.x-a.x)**2+(b.y-a.y)**2;
    return dot <= lengthSquared+epsilon;
  }

  function pointOnPolygon(point, poly) {
    return poly.some((a,index) => pointOnSegment(point,a,poly[(index+1)%poly.length]));
  }

  function pointStrictlyInside(point, poly) {
    return !pointOnPolygon(point,poly) && pointInPolygon(point,poly);
  }

  function orientation(a,b,c) {
    return (b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x);
  }

  function properSegmentsIntersect(a,b,c,d) {
    const o1 = orientation(a,b,c);
    const o2 = orientation(a,b,d);
    const o3 = orientation(c,d,a);
    const o4 = orientation(c,d,b);
    return ((o1>EPSILON&&o2<-EPSILON)||(o1<-EPSILON&&o2>EPSILON)) &&
      ((o3>EPSILON&&o4<-EPSILON)||(o3<-EPSILON&&o4>EPSILON));
  }

  function polygonEdgesIntersect(a,b) {
    for (let i=0;i<a.length;i+=1) {
      for (let j=0;j<b.length;j+=1) {
        if (properSegmentsIntersect(a[i],a[(i+1)%a.length],b[j],b[(j+1)%b.length])) return true;
      }
    }
    return false;
  }

  function segmentBreakpoints(a,b,poly) {
    const dx=b.x-a.x,dy=b.y-a.y;
    const denominatorLength=dx*dx+dy*dy;
    const values=[0,1];
    poly.forEach((c,index)=>{
      const d=poly[(index+1)%poly.length];
      const ex=d.x-c.x,ey=d.y-c.y;
      const denominator=dx*ey-dy*ex;
      if (Math.abs(denominator)>EPSILON) {
        const qx=c.x-a.x,qy=c.y-a.y;
        const t=(qx*ey-qy*ex)/denominator;
        const u=(qx*dy-qy*dx)/denominator;
        if (t>=-EPSILON&&t<=1+EPSILON&&u>=-EPSILON&&u<=1+EPSILON) values.push(clamp(t,0,1));
      } else if (Math.abs(orientation(a,b,c))<=EPSILON&&denominatorLength>EPSILON) {
        [c,d].forEach((point)=>{
          const t=((point.x-a.x)*dx+(point.y-a.y)*dy)/denominatorLength;
          if (t>=-EPSILON&&t<=1+EPSILON) values.push(clamp(t,0,1));
        });
      }
    });
    return values.sort((x,y)=>x-y).filter((value,index,array)=>index===0||Math.abs(value-array[index-1])>EPSILON);
  }

  function segmentIntervalsPass(a,b,poly,predicate) {
    const breaks=segmentBreakpoints(a,b,poly);
    for (let i=0;i<breaks.length-1;i+=1) {
      if (breaks[i+1]-breaks[i]<=EPSILON) continue;
      const t=(breaks[i]+breaks[i+1])/2;
      const point={x:a.x+(b.x-a.x)*t,y:a.y+(b.y-a.y)*t};
      if (!predicate(point,poly)) return false;
    }
    return true;
  }

  function polygonsOverlap(a,b) {
    if (polygonEdgesIntersect(a,b)) return true;
    if (a.some((point) => pointStrictlyInside(point,b))) return true;
    if (b.some((point) => pointStrictlyInside(point,a))) return true;
    return false;
  }

  function polygonInsideSite(poly,outer,holes=[]) {
    if (poly.some((point) => !pointInPolygon(point,outer) && !pointOnPolygon(point,outer))) return false;
    for (let i=0;i<poly.length;i+=1) {
      const a = poly[i];
      const b = poly[(i+1)%poly.length];
      if (!segmentIntervalsPass(a,b,outer,(point,boundary)=>pointInPolygon(point,boundary)||pointOnPolygon(point,boundary))) return false;
    }
    for (const hole of holes) {
      if (polygonEdgesIntersect(poly,hole)) return false;
      if (poly.some((point) => pointStrictlyInside(point,hole))) return false;
      if (hole.some((point) => pointStrictlyInside(point,poly))) return false;
      for (let i=0;i<poly.length;i+=1) {
        const a=poly[i];
        const b=poly[(i+1)%poly.length];
        if (!segmentIntervalsPass(a,b,hole,(point,boundary)=>!pointStrictlyInside(point,boundary))) return false;
      }
    }
    return true;
  }

  function boundsOf(poly) {
    const xs = poly.map((p) => p.x);
    const ys = poly.map((p) => p.y);
    return { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) };
  }

  function rotatePolygon(poly, angleDegrees) {
    const angle=angleDegrees*Math.PI/180;
    const cosine=Math.cos(angle),sine=Math.sin(angle);
    const rotated=poly.map((point)=>({x:point.x*cosine-point.y*sine,y:point.x*sine+point.y*cosine}));
    const b = boundsOf(rotated);
    return rotated.map((p) => ({ x: p.x - b.minX, y: p.y - b.minY }));
  }

  function rasterizePolygon(poly) {
    const b = boundsOf(poly);
    const cells = [];
    for (let y = Math.floor(b.minY); y < Math.ceil(b.maxY); y += 1) {
      for (let x = Math.floor(b.minX); x < Math.ceil(b.maxX); x += 1) {
        if (pointInPolygon({ x: x + 0.5, y: y + 0.5 }, poly)) cells.push({ x, y });
      }
    }
    return cells;
  }

  function normalizeRotations(poly,angleStep) {
    const rotations = [];
    const signatures = new Set();
    const steps=Math.max(1,Math.round(360/angleStep));
    for (let rotation = 0; rotation < steps; rotation += 1) {
      const angle=rotation*angleStep;
      const rotatedPoly = rotatePolygon(poly,angle);
      const cells = rasterizePolygon(rotatedPoly);
      const signature=rotatedPoly.map((point)=>`${point.x.toFixed(3)},${point.y.toFixed(3)}`).join('|');
      if (signatures.has(signature)) continue;
      signatures.add(signature);
      const b = boundsOf(rotatedPoly);
      rotations.push({ rotation, angle, poly: rotatedPoly, cells, width: b.maxX - b.minX, height: b.maxY - b.minY });
    }
    return rotations;
  }

  function convexHull(points) {
    const sorted = points.slice().sort((a,b) => a.x===b.x?a.y-b.y:a.x-b.x);
    if (sorted.length<=3) return sorted;
    const half = [];
    const append = (point) => {
      while (half.length>=2 && orientation(half[half.length-2],half[half.length-1],point)<=0) half.pop();
      half.push(point);
    };
    sorted.forEach(append);
    const lower = half.slice(0,-1);
    half.length=0;
    sorted.slice().reverse().forEach(append);
    return lower.concat(half.slice(0,-1));
  }

  function translateToOrigin(poly) {
    const b = boundsOf(poly);
    return poly.map((point) => ({x:point.x-b.minX,y:point.y-b.minY}));
  }

  function makeBoundary(type,seed,options={}) {
    const rng = new RNG(seed);
    let outer;
    let family = type;
    if (type === 'lshape') {
      const w = rng.int(29, 35);
      const h = rng.int(23, 28);
      const cutW = rng.int(10, 14);
      const cutH = rng.int(9, 13);
      outer = [{x:0,y:0},{x:w,y:0},{x:w,y:h-cutH},{x:w-cutW,y:h-cutH},{x:w-cutW,y:h},{x:0,y:h}];
    } else if (type === 'ushape') {
      const w = rng.int(32, 38);
      const h = rng.int(23, 28);
      const arm = rng.int(7, 9);
      const courtDepth = rng.int(10, 14);
      outer = [{x:0,y:0},{x:w,y:0},{x:w,y:h},{x:w-arm,y:h},{x:w-arm,y:h-courtDepth},{x:arm,y:h-courtDepth},{x:arm,y:h},{x:0,y:h}];
    } else if (type === 'convex') {
      const w=rng.int(32,40),h=rng.int(23,30);
      const points=[];
      for (let i=0;i<22;i+=1) points.push({x:rng.int(0,w),y:rng.int(0,h)});
      points.push({x:0,y:rng.int(5,h-5)},{x:w,y:rng.int(5,h-5)},{x:rng.int(5,w-5),y:0},{x:rng.int(5,w-5),y:h});
      outer=translateToOrigin(convexHull(points));
      family='convex hull';
    } else if (type === 'tshape') {
      const w=rng.int(31,39),bar=rng.int(7,10),stemW=rng.int(11,16),stemH=rng.int(15,21);
      const stemX=rng.int(5,w-stemW-5);
      outer=[{x:0,y:0},{x:w,y:0},{x:w,y:bar},{x:stemX+stemW,y:bar},{x:stemX+stemW,y:bar+stemH},{x:stemX,y:bar+stemH},{x:stemX,y:bar},{x:0,y:bar}];
      family='randomized T';
    }else if(type==='lobed'){
      const count=clamp(Math.round(options.boundaryVertices??rng.int(13,19)),10,24);
      const lobeCount=clamp(Math.round(options.lobeCount??rng.int(3,6)),2,Math.floor(count/2));
      const reach=clamp(Number(options.lobeReach??1.55),1.1,2.2);
      const notchDepth=clamp(Number(options.concavity??.62),.25,.82);
      const globalRotation=rng.next()*TAU;
      const aspectAngle=rng.next()*TAU;
      const rx=rng.int(14,18),ry=rng.int(11,16),cx=20,cy=18;
      const indices=Array.from({length:count},(_,index)=>index);
      rng.shuffle(indices);
      const lobes=[];
      for(const candidate of indices){
        if(lobes.every((index)=>Math.min(Math.abs(index-candidate),count-Math.abs(index-candidate))>=2))lobes.push(candidate);
        if(lobes.length>=lobeCount)break;
      }
      const lobeSet=new Set(lobes);
      const notches=new Set();
      lobes.forEach((index,lobeIndex)=>{
        const direction=lobeIndex%2===0?1:-1;
        notches.add((index+direction+count)%count);
        if(lobeIndex<Math.ceil(lobeCount/2))notches.add((index-direction+count)%count);
      });
      outer=[];
      for(let i=0;i<count;i+=1){
        const angle=globalRotation+(i/count)*TAU+(rng.next()-.5)*.07;
        let radius=.76+rng.next()*.25;
        if(lobeSet.has(i))radius=reach*(.78+rng.next()*.34);
        if(notches.has(i))radius=1-notchDepth*(.72+rng.next()*.22);
        const localX=Math.cos(angle)*rx*radius,localY=Math.sin(angle)*ry*radius;
        const anisotropy=.82+rng.next()*.18;
        outer.push({
          x:cx+(localX*Math.cos(aspectAngle)-localY*Math.sin(aspectAngle))*anisotropy,
          y:cy+localX*Math.sin(aspectAngle)+localY*Math.cos(aspectAngle)
        });
      }
      outer=translateToOrigin(outer);
      family='deep-lobed star';
    } else if (type === 'concave' || type === 'free') {
      if (type==='free') family=rng.pick(['convex','concave','tshape','lobed']);
      else family='non-convex radial';
      if (family==='convex') return makeBoundary('convex',seed^0x513,options);
      if (family==='tshape') return makeBoundary('tshape',seed^0x891,options);
      if(family==='lobed')return makeBoundary('lobed',seed^0xA71,options);
      const count=rng.int(9,13),cx=18,cy=14,rx=rng.int(15,19),ry=rng.int(11,14);
      outer=[];
      for (let i=0;i<count;i+=1) {
        const angle=-Math.PI/2+(i/count)*TAU+rng.next()*.08;
        const inset=(i===2||i===Math.floor(count*.58))?rng.next()*.22+.48:rng.next()*.18+.82;
        outer.push({x:cx+Math.cos(angle)*rx*inset,y:cy+Math.sin(angle)*ry*inset});
      }
      outer=translateToOrigin(outer);
    } else {
      const w = rng.int(32, 38);
      const h = rng.int(21, 27);
      outer = [{x:0,y:0},{x:w,y:0},{x:w,y:h},{x:0,y:h}];
    }
    return { outer, seed, type, family };
  }

  function atriumCandidates(boundary) {
    const b = boundsOf(boundary.outer);
    const center = polygonCentroid(boundary.outer);
    const w = b.maxX - b.minX;
    const h = b.maxY - b.minY;
    const aw = clamp(Math.round(w * 0.18), 4, 7);
    const ah = clamp(Math.round(h * 0.22), 4, 6);
    const central = [
      {x:Math.round(center.x-aw/2),y:Math.round(center.y-ah/2)},
      {x:Math.round(center.x+aw/2),y:Math.round(center.y-ah/2)},
      {x:Math.round(center.x+aw/2),y:Math.round(center.y+ah/2)},
      {x:Math.round(center.x-aw/2),y:Math.round(center.y+ah/2)}
    ];
    const splitW = Math.max(3, Math.round(aw * .7));
    const splitH = Math.max(3, Math.round(ah * .75));
    const left = [
      {x:Math.round(center.x-aw),y:Math.round(center.y-splitH/2)},
      {x:Math.round(center.x-aw+splitW),y:Math.round(center.y-splitH/2)},
      {x:Math.round(center.x-aw+splitW),y:Math.round(center.y+splitH/2)},
      {x:Math.round(center.x-aw),y:Math.round(center.y+splitH/2)}
    ];
    const right = left.map((p) => ({ x: 2 * center.x - p.x, y: p.y }));
    const valid = (hole) => polygonInsideSite(hole,boundary.outer,[]);
    return [
      { id: 'none', label: 'No atrium', holes: [] },
      { id: 'central', label: 'Central atrium', holes: valid(central) ? [central] : [] },
      { id: 'split', label: 'Split light wells', holes: valid(left) && valid(right) ? [left, right] : [] }
    ];
  }

  function buildSite(boundary, holes) {
    const outerBounds = boundsOf(boundary.outer);
    const cells = [];
    const cellSet = new Set();
    for (let y = Math.floor(outerBounds.minY); y < Math.ceil(outerBounds.maxY); y += 1) {
      for (let x = Math.floor(outerBounds.minX); x < Math.ceil(outerBounds.maxX); x += 1) {
        const center = { x: x + .5, y: y + .5 };
        if (!pointInPolygon(center, boundary.outer)) continue;
        if (holes.some((hole) => pointInPolygon(center, hole))) continue;
        const cell = { x, y };
        cells.push(cell);
        cellSet.add(key(x, y));
      }
    }

    const makeDistanceField=(seedPredicate)=>{
      const field=new Map(),queue=[];
      cells.forEach((cell)=>{if(seedPredicate(cell)){field.set(key(cell.x,cell.y),0);queue.push(cell);}});
      for(let index=0;index<queue.length;index+=1){
        const current=queue[index],nextDistance=field.get(key(current.x,current.y))+1;
        [[1,0],[-1,0],[0,1],[0,-1]].forEach(([dx,dy])=>{
          const nx=current.x+dx,ny=current.y+dy,nk=key(nx,ny);
          if(!cellSet.has(nk)||field.has(nk))return;
          field.set(nk,nextDistance);queue.push({x:nx,y:ny});
        });
      }
      return field;
    };
    const touchesOuter=(cell)=>[[1,0],[-1,0],[0,1],[0,-1]].some(([dx,dy])=>{
      const point={x:cell.x+dx+.5,y:cell.y+dy+.5};
      return !pointInPolygon(point,boundary.outer)&&!pointOnPolygon(point,boundary.outer);
    });
    const touchesAtrium=(cell)=>holes.some((hole)=>[[1,0],[-1,0],[0,1],[0,-1]].some(([dx,dy])=>pointInPolygon({x:cell.x+dx+.5,y:cell.y+dy+.5},hole)));
    const outerDistance=makeDistanceField(touchesOuter);
    const atriumDistance=holes.length?makeDistanceField(touchesAtrium):new Map();
    const distance=makeDistanceField((cell)=>touchesOuter(cell)||touchesAtrium(cell));
    return {
      outer: boundary.outer,
      holes,
      cells,
      cellSet,
      distance,
      outerDistance,
      atriumDistance,
      bounds: outerBounds,
      area: cells.length,
      exactArea: polygonArea(boundary.outer)-holes.reduce((sum,hole)=>sum+polygonArea(hole),0),
      outerPerimeter: polygonPerimeter(boundary.outer),
      innerPerimeter:holes.reduce((sum,hole)=>sum+polygonPerimeter(hole),0),
      reflexVertices:reflexVertexCount(boundary.outer),
      convexityRatio:polygonArea(boundary.outer)/Math.max(EPSILON,polygonArea(convexHull(boundary.outer)))
    };
  }

  function rectangle(w, h) { return [{x:0,y:0},{x:w,y:0},{x:w,y:h},{x:0,y:h}]; }
  function lModule(w, h, thickness) { return [{x:0,y:0},{x:w,y:0},{x:w,y:thickness},{x:thickness,y:thickness},{x:thickness,y:h},{x:0,y:h}]; }
  function chamfered(w, h, cut) { return [{x:cut,y:0},{x:w-cut,y:0},{x:w,y:cut},{x:w,y:h-cut},{x:w-cut,y:h},{x:cut,y:h},{x:0,y:h-cut},{x:0,y:cut}]; }
  function shearPolygon(poly,angleDegrees) {
    const factor=Math.tan(angleDegrees*Math.PI/180);
    return poly.map((point)=>({x:point.x+factor*point.y,y:point.y}));
  }

  function edgeLengths(poly) {
    return poly.map((p, i) => {
      const q = poly[(i+1)%poly.length];
      return Math.hypot(q.x-p.x, q.y-p.y);
    });
  }

  function polygonAngles(poly) {
    return poly.map((point,index) => {
      const previous=poly[(index-1+poly.length)%poly.length];
      const next=poly[(index+1)%poly.length];
      const a={x:previous.x-point.x,y:previous.y-point.y};
      const b={x:next.x-point.x,y:next.y-point.y};
      const cosine=clamp((a.x*b.x+a.y*b.y)/(Math.hypot(a.x,a.y)*Math.hypot(b.x,b.y)),-1,1);
      return Math.acos(cosine)*180/Math.PI;
    });
  }

  function moduleRegularity(poly) {
    const b=boundsOf(poly),width=b.maxX-b.minX,height=b.maxY-b.minY;
    const aspect=Math.min(width,height)/Math.max(width,height);
    const compact=clamp((4*Math.PI*polygonArea(poly))/(polygonPerimeter(poly)**2)/.785,0,1);
    const lengths=edgeLengths(poly),mean=lengths.reduce((s,v)=>s+v,0)/lengths.length;
    const variance=lengths.reduce((s,v)=>s+(v-mean)**2,0)/lengths.length;
    const edgeHarmony=clamp(1-Math.sqrt(variance)/Math.max(mean,EPSILON),0,1);
    const angles=polygonAngles(poly);
    const orthogonality=angles.filter((angle)=>Math.abs(angle-90)<1||Math.abs(angle-135)<1).length/angles.length;
    return .3*aspect+.35*compact+.2*edgeHarmony+.15*orthogonality;
  }

  function makeModule(id, name, category, poly, family,angleStep) {
    const rotations = normalizeRotations(poly,angleStep);
    return {
      id,
      name,
      category,
      family,
      poly,
      rotations,
      sides: poly.length,
      area: polygonArea(poly),
      edgeLengths: edgeLengths(poly),
      angles: polygonAngles(poly),
      regularity: moduleRegularity(poly),
      uses: 0
    };
  }

  function createModuleDictionary(settings, seed) {
    const rng = new RNG(seed ^ 0xA57C91);
    const min = Math.max(1, Math.ceil(settings.minEdge));
    const max = Math.max(min,Math.floor(settings.maxEdge));
    const short = clamp(rng.int(Math.max(min+1,3),Math.max(min+1,Math.min(max-1,5))),min+1,max);
    const long = clamp(Math.round(short*1.5),short,max);
    const square = clamp(short+1,min+1,max);
    const candidates = [];
    if (!settings.singleFloor) {
      const corridorWidth=Math.max(min,2);
      candidates.push(makeModule('C1','Service core','core',rectangle(square,square),'square',settings.angleStep));
      candidates.push(makeModule('T1','Linear link','corridor',rectangle(long,corridorWidth),'linear',settings.angleStep));
      if(settings.allowShear!==false)candidates.push(makeModule('T2','Splayed link','corridor',shearPolygon(rectangle(long,corridorWidth),settings.angleStep),'sheared',settings.angleStep));
      const bend=Math.min(max,Math.max(long,corridorWidth+min));
      if (settings.maxEdges>=6&&bend>=corridorWidth+min) candidates.push(makeModule('T3','Elbow link','corridor',lModule(bend,bend,corridorWidth),'elbow',settings.angleStep));
    }
    const roomStart = settings.singleFloor ? 0 : 2;
    const roomSpecs=[
      ['Proportion bay',rectangle(long,short),'3:2'],
      ['Square bay',rectangle(square,square),'square'],
      ['Compact bay',rectangle(short,Math.max(min+1,short-1)),'compact'],
      ['Long bay',rectangle(max,short),'linear'],
      ['Paired bay',rectangle(long,Math.min(max,short+1)),'paired'],
      ['Balanced bay',rectangle(Math.min(max,square+1),square),'balanced']
    ];
    const triangleLeg=Math.min(max,Math.max(min,4));
    roomSpecs.push(['Tip infill',[{x:0,y:0},{x:triangleLeg,y:0},{x:0,y:triangleLeg}],'triangle']);
    if (settings.maxEdges>=6) {
      const cut=Math.max(1,Math.ceil(min/Math.SQRT2));
      roomSpecs.push(['Clipped bay',[{x:cut,y:0},{x:long,y:0},{x:long,y:short-cut},{x:long-cut,y:short},{x:0,y:short},{x:0,y:cut}],'dual-chamfer']);
      const thickness=clamp(min,1,Math.min(short-1,long-1));
      roomSpecs.push(['Corner bay',lModule(long,short,thickness),'L']);
    }
    if (settings.maxEdges>=8) {
      const cut=Math.max(1,Math.ceil(min/Math.SQRT2));
      if (square>=2*cut+min) roomSpecs.push(['Soft octagon',chamfered(square,square,cut),'octagon']);
    }
    if(settings.allowShear!==false)roomSpecs.push(['Splayed room',shearPolygon(rectangle(long,short),settings.angleStep),'sheared']);
    roomSpecs.forEach((spec,index)=>candidates.push(makeModule(`R${index+1}`,spec[0],'room',spec[1],spec[2],settings.angleStep)));

    const edgeValid=candidates.filter((module) => {
      const validEdges = module.edgeLengths.every((length) => length >= settings.minEdge - .01 && length <= settings.maxEdge + .01);
      const validAngles=module.angles.every((angle)=>{
        const stepped=Math.abs(angle/settings.angleStep-Math.round(angle/settings.angleStep))<1e-6;
        return angle>=40-.01&&stepped;
      });
      return validEdges&&validAngles&&module.sides<=settings.maxEdges;
    });
    const maxArea=Math.max(1,...edgeValid.map((module)=>module.area));
    const viable=edgeValid.filter((module)=>module.area/maxArea>=.2);
    const core=viable.filter((module)=>module.category==='core').slice(0,1);
    const corridorLimit=settings.dictCap>=6?2:1;
    const corridors=viable.filter((module)=>module.category==='corridor').sort((a,b)=>b.regularity-a.regularity).slice(0,corridorLimit);
    const mustHave=settings.singleFloor?[]:core.concat(corridors);
    const rooms = viable.filter((m) => m.category === 'room').sort((a,b)=>b.regularity-a.regularity || a.area-b.area);
    const roomSlots=Math.max(0,settings.dictCap-mustHave.length);
    const selectedRooms=rooms.slice(0,roomSlots);
    if(settings.allowShear!==false&&!mustHave.some((module)=>module.family==='sheared')&&!selectedRooms.some((module)=>module.family==='sheared')){
      const shearedRoom=rooms.find((module)=>module.family==='sheared');
      if(shearedRoom&&selectedRooms.length)selectedRooms[selectedRooms.length-1]=shearedRoom;
    }
    const compactRoom=rooms.reduce((best,module)=>!best||module.area<best.area?module:best,null);
    if(compactRoom&&selectedRooms.length&&!selectedRooms.some((module)=>module.id===compactRoom.id)){
      const replacementIndex=Math.max(0,selectedRooms.length-2);
      selectedRooms[replacementIndex]=compactRoom;
    }
    const result=mustHave.concat(selectedRooms).slice(0,settings.dictCap);
    result.forEach((module, index) => { module.index = index; });
    return result;
  }

  global.ModGeometry = {
    RNG,
    TAU,
    key,
    clamp,
    polygonArea,
    reflexVertexCount,
    polygonPerimeter,
    polygonCentroid,
    pointInPolygon,
    pointOnPolygon,
    pointStrictlyInside,
    polygonsOverlap,
    polygonInsideSite,
    rasterizePolygon,
    boundsOf,
    makeBoundary,
    atriumCandidates,
    buildSite,
    createModuleDictionary
  };
})(window);
