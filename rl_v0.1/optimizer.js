(function (global) {
  'use strict';

  const G = global.ModGeometry;
  const DIRECTIONS = [[1,0],[-1,0],[0,1],[0,-1]];
  const FEATURE_NAMES = ['coverage','contact','reuse','daylight','compactness','regularity','orientation','circulation','atrium','novelty','travel','sequence'];

  class ModularRLAgent {
    constructor(settings, seed) {
      this.settings = { ...settings };
      this.seed = seed || Date.now();
      this.rng = new G.RNG(this.seed);
      this.weights = {
        coverage: 0.85,
        contact: 0.72,
        reuse: 0.42,
        daylight: 0.18,
        compactness: 0.38,
        regularity: 0.44,
        orientation: 0.52,
        circulation: 0.68,
        atrium: 0.22,
        novelty: 0.34,
        travel: 0.28,
        sequence: 0.46
      };
      this.atriumValues = { none: 0, central: 0, split: 0 };
      this.baseline = 0.42;
      this.episode = 0;
      this.scoreHistory = [];
      this.bestScore = 0;
      this.lastScore = 0;
      this.lastReward = 0;
      this.resetEnvironment(true);
    }

    updateSettings(settings, rebuild = false) {
      this.settings = { ...settings };
      if (rebuild) this.resetEnvironment(true);
    }

    resetPolicy() {
      this.weights={coverage:.85,contact:.72,reuse:.42,daylight:.18,compactness:.38,regularity:.44,orientation:.52,circulation:.68,atrium:.22,novelty:.34,travel:.28,sequence:.46};
      this.atriumValues = { none:0, central:0, split:0 };
      this.baseline = .42;
      this.scoreHistory = [];
      this.bestScore = 0;
      this.lastScore = 0;
      this.resetEnvironment(true);
    }

    chooseAtrium(candidates) {
      if (this.settings.atriumPolicy === 'none') return candidates[0];
      if (this.settings.atriumPolicy === 'central') return candidates.find((c) => c.id === 'central') || candidates[0];
      const epsilon = Math.max(.08, .34 * Math.exp(-this.episode / 18));
      if (this.rng.next() < epsilon) return this.rng.pick(candidates);
      return candidates.reduce((best, candidate) => this.atriumValues[candidate.id] > this.atriumValues[best.id] ? candidate : best, candidates[0]);
    }

    resetEnvironment(newSite = false) {
      if (newSite || !this.boundary) {
        this.siteSeed = Math.floor(this.rng.next() * 0x7fffffff);
        this.boundary=G.makeBoundary(this.settings.boundaryType,this.siteSeed,this.settings);
      }
      const candidates=G.atriumCandidates(this.boundary).filter((candidate)=>candidate.id==='none'||candidate.holes.length>0);
      this.atriumChoice = this.chooseAtrium(candidates);
      this.site = G.buildSite(this.boundary, this.atriumChoice.holes);
      this.dictionary = G.createModuleDictionary(this.settings, this.siteSeed + this.episode * 7919);
      this.dictionary.forEach((module) => { module.uses = 0; });
      const orientationSteps=Math.max(1,Math.round(90/this.settings.angleStep));
      this.episodeOrientation=this.settings.orientationMode==='orthogonal'?0:this.rng.int(0,orientationSteps-1)*this.settings.angleStep;
      this.placements = [];
      this.occupied = new Map();
      this.trace = [];
      this.stepCount = 0;
      this.done = false;
      this.stalled = false;
      this.currentReward = 0;
      this.metrics = this.computeMetrics();
      this.maxModuleArea = Math.max(1, ...this.dictionary.map((m) => m.area));
    }

    newEpisode() {
      this.episode += 1;
      this.resetEnvironment(false);
    }

    newSite() {
      this.resetEnvironment(true);
    }

    frontierCells() {
      if (!this.occupied.size) {
        const center = G.polygonCentroid(this.site.outer);
        return this.site.cells
          .slice()
          .sort((a,b)=>(this.site.distance.get(G.key(b.x,b.y))??0)-(this.site.distance.get(G.key(a.x,a.y))??0)||Math.hypot(a.x+.5-center.x,a.y+.5-center.y)-Math.hypot(b.x+.5-center.x,b.y+.5-center.y))
          .slice(0,60);
      }
      const seen = new Set();
      const frontier = [];
      this.occupied.forEach((_, occupiedKey) => {
        const [x,y] = occupiedKey.split(',').map(Number);
        DIRECTIONS.forEach(([dx,dy]) => {
          const nx = x+dx;
          const ny = y+dy;
          const nk = G.key(nx,ny);
          if (seen.has(nk) || this.occupied.has(nk) || !this.site.cellSet.has(nk)) return;
          seen.add(nk);
          frontier.push({x:nx,y:ny});
        });
      });
      return this.rng.shuffle(frontier).slice(0,36);
    }

    candidateFor(module, rotation, anchorX, anchorY) {
      const worldPoly=rotation.poly.map((point)=>({x:point.x+anchorX,y:point.y+anchorY}));
      if (!G.polygonInsideSite(worldPoly,this.site.outer,this.site.holes)) return null;
      if (this.placements.some((placement)=>G.polygonsOverlap(worldPoly,placement.poly))) return null;
      const cells=G.rasterizePolygon(worldPoly);
      if(!cells.length)return null;
      for (const cell of cells) {
        const cellKey = G.key(cell.x,cell.y);
        if (!this.site.cellSet.has(cellKey) || this.occupied.has(cellKey)) return null;
      }

      let contactEdges = 0;
      let externalEdges = 0;
      let daylightCells = 0;
      let outerEdgeCells=0;
      let atriumProximity=0;
      const touchingIds=new Set();
      const candidateSet = new Set(cells.map((cell) => G.key(cell.x,cell.y)));
      cells.forEach((cell) => {
        if ((this.site.distance.get(G.key(cell.x,cell.y)) || 0) <= 6) daylightCells += 1;
        if ((this.site.outerDistance.get(G.key(cell.x,cell.y))??999)===0) outerEdgeCells+=1;
        if (this.site.holes.length) atriumProximity+=1/(1+(this.site.atriumDistance.get(G.key(cell.x,cell.y))??20));
        DIRECTIONS.forEach(([dx,dy]) => {
          const neighbor = G.key(cell.x+dx,cell.y+dy);
          if (this.occupied.has(neighbor)) {contactEdges += 1;touchingIds.add(this.occupied.get(neighbor));}
          if (!candidateSet.has(neighbor) && !this.occupied.has(neighbor)) externalEdges += 1;
        });
      });

      const outerExposure=outerEdgeCells/cells.length;
      if(module.category==='corridor'&&outerExposure>.35)return null;

      const center=G.polygonCentroid(worldPoly);
      const coreCenters = this.placements.filter((p) => p.module.category === 'core').map((p) => p.center);
      const roomCount=this.placements.filter((placement)=>placement.module.category==='room').length;
      if(!this.settings.singleFloor){
        if(!coreCenters.length&&module.category!=='core')return null;
        if(coreCenters.length&&module.category==='core')return null;
        if(module.category==='corridor'&&roomCount<2)return null;
      }
      let travelFeature = this.settings.singleFloor ? .5 : -1;
      if (module.category === 'core') {
        travelFeature = coreCenters.length ? -.5 : 1;
      } else if (coreCenters.length) {
        const distance = Math.min(...coreCenters.map((core) => Math.hypot(core.x-center.x, core.y-center.y)));
        travelFeature = G.clamp(1 - distance / this.settings.travelLimit, -1, 1);
      }

      const hasCore = coreCenters.length > 0;
      const hasCorridor = this.placements.some((p) => p.module.category === 'corridor');
      let sequence = .15;
      if (!this.settings.singleFloor) {
        if (!hasCore) sequence = module.category === 'core' ? 1 : -.9;
        else if(roomCount<2)sequence=module.category==='room'?.9:module.category==='corridor'?-.55:-.7;
        else if(!hasCorridor)sequence=module.category==='corridor'?.8:module.category==='room'?.35:-.7;
        else if(module.category==='room')sequence=.45;
      }
      const neighborCategories=new Set([...touchingIds].map((id)=>this.placements[id]?.module.category).filter(Boolean));
      if(module.category==='corridor'&&(touchingIds.size<1||(!neighborCategories.has('room')&&!neighborCategories.has('core'))))return null;
      let circulation=.25;
      if(module.category==='corridor'){
        const degree=G.clamp(touchingIds.size/2,0,1);
        const bridge=touchingIds.size>=2&&(neighborCategories.has('room')||neighborCategories.has('core'))?1:0;
        circulation=.42*degree+.36*(1-outerExposure)+.22*bridge;
      }else if(module.category==='room'){
        circulation=neighborCategories.has('corridor')?.9:neighborCategories.has('room')?.55:neighborCategories.has('core')?.4:.2;
      }else if(module.category==='core')circulation=coreCenters.length?-.5:.7;
      const angle=rotation.angle%180;
      const basisDelta=Math.abs(angle-this.episodeOrientation);
      const orientation=1-Math.min(basisDelta,180-basisDelta)/90;
      const orthogonalRemainder=angle%90;
      const nonOrthogonality=Math.min(orthogonalRemainder,90-orthogonalRemainder)/45;
      const formalNovelty=['sheared','elbow','dual-chamfer','octagon','L'].includes(module.family)?1:.15;
      const novelty=.62*nonOrthogonality+.38*formalNovelty;
      const atrium=this.site.holes.length?G.clamp(atriumProximity/cells.length*(module.category==='corridor'?2.4:1.5),0,1):.55;
      const features = {
        coverage: module.area/this.maxModuleArea,
        contact: G.clamp(contactEdges / Math.max(2, Math.sqrt(cells.length) * 2), 0, 1),
        reuse: module.uses > 0 ? G.clamp(module.uses / 4, .25, 1) : -.3,
        daylight: daylightCells / cells.length,
        compactness: G.clamp(contactEdges / Math.max(1, externalEdges), 0, 1),
        regularity: module.regularity,
        orientation,
        circulation,
        atrium,
        novelty,
        travel: travelFeature,
        sequence
      };
      let logit=FEATURE_NAMES.reduce((sum,name)=>sum+this.weights[name]*features[name],0);
      if(!this.placements.length)logit+=2.4*orientation;
      const fillProgress=this.placements.length?this.placements.reduce((sum,placement)=>sum+placement.module.area,0)/this.site.exactArea:0;
      logit+=G.clamp(fillProgress,0,1)*1.15*(1-module.area/this.maxModuleArea);
      if(module.family==='triangle')logit-=.7*(1-G.clamp((fillProgress-.35)/.35,0,1));
      if(this.settings.allowShear!==false&&module.family==='sheared'){
        const shearRate=this.placements.length?this.placements.filter((placement)=>placement.module.family==='sheared').length/this.placements.length:0;
        logit+=.95*G.clamp(1-shearRate/.18,0,1);
      }
      return {module,rotation,worldPoly,anchorX,anchorY,cells,center,contactEdges,externalEdges,touchingIds:[...touchingIds],features,logit};
    }

    candidateRotations(module){
      const basis=this.episodeOrientation%90;
      const coherent=module.rotations.filter((rotation)=>{
        const remainder=rotation.angle%90,delta=Math.abs(remainder-basis);
        const tolerance=this.settings.orientationMode==='orthogonal'?.001:this.settings.angleStep+.001;
        return Math.min(delta,90-delta)<=tolerance;
      });
      return this.rng.shuffle((coherent.length?coherent:module.rotations).slice()).slice(0,10);
    }

    edgeAlignedCandidates(modules,seen,limit){
      if(!this.placements.length||this.settings.edgeAlignment===false)return[];
      const candidates=[];
      const hosts=this.rng.shuffle(this.placements.slice(-20));
      for(const host of hosts){
        for(let targetIndex=0;targetIndex<host.poly.length;targetIndex+=1){
          const a=host.poly[targetIndex],b=host.poly[(targetIndex+1)%host.poly.length];
          const targetLength=Math.hypot(b.x-a.x,b.y-a.y);
          for(const module of modules){
            for(const rotation of this.candidateRotations(module)){
              for(let edgeIndex=0;edgeIndex<rotation.poly.length;edgeIndex+=1){
                const c=rotation.poly[edgeIndex],d=rotation.poly[(edgeIndex+1)%rotation.poly.length];
                if(Math.abs(Math.hypot(d.x-c.x,d.y-c.y)-targetLength)>.04)continue;
                const anchorX=b.x-c.x,anchorY=b.y-c.y;
                if(Math.hypot(d.x+anchorX-a.x,d.y+anchorY-a.y)>.04)continue;
                const signature=`${module.id}|${rotation.angle}|${anchorX.toFixed(3)}|${anchorY.toFixed(3)}`;
                if(seen.has(signature))continue;
                seen.add(signature);
                const candidate=this.candidateFor(module,rotation,anchorX,anchorY);
                if(candidate){candidate.logit+=.52;candidate.edgeAligned=true;candidates.push(candidate);}
                if(candidates.length>=limit)return candidates;
              }
            }
          }
        }
      }
      return candidates;
    }

    generateCandidates() {
      const frontier = this.frontierCells();
      const candidates = [];
      const seen = new Set();
      const modules = this.rng.shuffle(this.dictionary.slice());
      candidates.push(...this.edgeAlignedCandidates(modules,seen,this.settings.edgeCandidateLimit??70));
      for (const target of frontier) {
        for (const module of modules) {
          const rotations=this.candidateRotations(module);
          for (const rotation of rotations) {
            const localChoices = rotation.cells.length <= 9
              ? rotation.cells
              : [rotation.cells[0], rotation.cells[Math.floor(rotation.cells.length/3)], rotation.cells[Math.floor(rotation.cells.length*2/3)], rotation.cells[rotation.cells.length-1]];
            for (const local of localChoices) {
              const anchorX = target.x - local.x;
              const anchorY = target.y - local.y;
              const signature=`${module.id}|${rotation.angle}|${anchorX.toFixed(3)}|${anchorY.toFixed(3)}`;
              if (seen.has(signature)) continue;
              seen.add(signature);
              const candidate = this.candidateFor(module,rotation,anchorX,anchorY);
              if (candidate) candidates.push(candidate);
              if(candidates.length>=(this.settings.candidateLimit??190))return candidates;
            }
          }
        }
      }
      return candidates;
    }

    sampleAction(candidates) {
      const temperature = Math.max(.28, .72 * Math.exp(-this.episode / 32));
      const maxLogit = Math.max(...candidates.map((c) => c.logit));
      const probabilities = candidates.map((candidate) => Math.exp((candidate.logit-maxLogit)/temperature));
      const total = probabilities.reduce((sum,value) => sum+value,0);
      let chosenIndex=probabilities.length-1;
      if(this.settings.greedyPolicy)chosenIndex=candidates.reduce((best,candidate,index)=>candidate.logit>candidates[best].logit?index:best,0);
      else{
        let cursor=this.rng.next()*total;
        for(let i=0;i<probabilities.length;i+=1){cursor-=probabilities[i];if(cursor<=0){chosenIndex=i;break;}}
      }
      const expected = {};
      FEATURE_NAMES.forEach((name) => { expected[name] = 0; });
      candidates.forEach((candidate,index) => {
        const probability = probabilities[index] / total;
        FEATURE_NAMES.forEach((name) => { expected[name] += candidate.features[name] * probability; });
      });
      const chosen = candidates[chosenIndex];
      const gradient = {};
      FEATURE_NAMES.forEach((name) => { gradient[name] = chosen.features[name] - expected[name]; });
      return { chosen, gradient };
    }

    place(action) {
      const placementId = this.placements.length;
      action.cells.forEach((cell) => this.occupied.set(G.key(cell.x,cell.y), placementId));
      action.module.uses += 1;
      this.placements.push({
        id: placementId,
        module: action.module,
        cells: action.cells,
        poly: action.worldPoly,
        center: action.center,
        rotation: action.rotation.angle,
        initialNeighbors:action.touchingIds,
        bornAt: performance.now()
      });
      const localReward=.23*action.features.coverage+.16*action.features.contact+.12*action.features.reuse+.08*action.features.daylight+.09*action.features.regularity+.1*action.features.orientation+.1*action.features.circulation+.05*action.features.atrium+.04*action.features.novelty+.03*action.features.sequence;
      this.currentReward = localReward;
      this.lastReward = localReward;
    }

    step() {
      if (this.done) return { done:true, metrics:this.metrics };
      if (this.placements.length >= this.settings.maxModules || this.occupied.size / this.site.area >= .985) return this.finishEpisode();
      const candidates = this.generateCandidates();
      if (!candidates.length) {
        this.stalled = true;
        return this.finishEpisode();
      }
      const sampled = this.sampleAction(candidates);
      this.place(sampled.chosen);
      this.trace.push(sampled.gradient);
      this.stepCount += 1;
      this.metrics = this.computeMetrics();
      return { done:false, placement:this.placements[this.placements.length-1], metrics:this.metrics };
    }

    connectedComponents() {
      const unseen = new Set(this.occupied.keys());
      let components = 0;
      while (unseen.size) {
        components += 1;
        const start = unseen.values().next().value;
        unseen.delete(start);
        const queue = [start];
        for (let i=0;i<queue.length;i+=1) {
          const [x,y] = queue[i].split(',').map(Number);
          DIRECTIONS.forEach(([dx,dy]) => {
            const next = G.key(x+dx,y+dy);
            if (unseen.delete(next)) queue.push(next);
          });
        }
      }
      return components;
    }

    placementAdjacency(){
      const adjacency=new Map();
      this.placements.forEach((placement)=>adjacency.set(placement.id,new Set()));
      this.occupied.forEach((placementId,occupiedKey)=>{
        const [x,y]=occupiedKey.split(',').map(Number);
        DIRECTIONS.forEach(([dx,dy])=>{
          const neighborId=this.occupied.get(G.key(x+dx,y+dy));
          if(neighborId!==undefined&&neighborId!==placementId){
            adjacency.get(placementId)?.add(neighborId);
            adjacency.get(neighborId)?.add(placementId);
          }
        });
      });
      return adjacency;
    }

    computeMetrics() {
      const filledArea=this.placements?this.placements.reduce((sum,placement)=>sum+G.polygonArea(placement.poly),0):0;
      const siteArea=this.site?this.site.exactArea:1;
      const fillRatio = filledArea / Math.max(1,siteArea);
      let exposedPerimeter = 0;
      let sharedEdges = 0;
      let daylightCells = 0;
      if (this.occupied) {
        this.occupied.forEach((_, occupiedKey) => {
          const [x,y] = occupiedKey.split(',').map(Number);
          if ((this.site.distance.get(occupiedKey) || 0) <= 6) daylightCells += 1;
          DIRECTIONS.forEach(([dx,dy]) => {
            const next = G.key(x+dx,y+dy);
            if (this.occupied.has(next)) sharedEdges += .5;
            else exposedPerimeter += 1;
          });
        });
      }
      const uses = this.dictionary ? this.dictionary.filter((m) => m.uses>0) : [];
      const dictionaryUsed = uses.length;
      const moduleCount = this.placements ? this.placements.length : 0;
      const reuse = moduleCount ? G.clamp((moduleCount-dictionaryUsed)/Math.max(1,moduleCount-1),0,1) : 0;
      const daylight=filledArea?G.clamp(daylightCells/filledArea,0,1):0;
      const envelopeEfficiency = filledArea ? exposedPerimeter/filledArea : 0;
      const compactness = filledArea ? G.clamp((4*Math.sqrt(filledArea))/Math.max(1,exposedPerimeter),0,1) : 0;
      const constructibility = filledArea ? G.clamp(.55*(sharedEdges/(sharedEdges+exposedPerimeter))/.5 + .45*(1-Math.max(0,dictionaryUsed-6)/10),0,1) : 0;
      const cores = this.placements ? this.placements.filter((p) => p.module.category==='core') : [];
      const rooms = this.placements ? this.placements.filter((p) => p.module.category==='room') : [];
      let averageTravel = 0;
      if (cores.length && rooms.length) {
        averageTravel = rooms.reduce((sum,room) => sum + Math.min(...cores.map((core) => Math.hypot(core.center.x-room.center.x,core.center.y-room.center.y))),0)/rooms.length;
      }
      const travelQuality = this.settings.singleFloor ? 1 : cores.length ? G.clamp(1-averageTravel/this.settings.travelLimit,0,1) : 0;
      const components = filledArea ? this.connectedComponents() : 0;
      const connectivity = components <= 1 ? 1 : 1/components;
      const sizeAreas = this.dictionary ? this.dictionary.map((m) => m.area) : [];
      const sizeRatio = sizeAreas.length ? Math.min(...sizeAreas)/Math.max(...sizeAreas) : 1;
      const regularity=moduleCount?this.placements.reduce((sum,placement)=>sum+placement.module.regularity,0)/moduleCount:0;
      const adjacency=this.placementAdjacency();
      const corridors=this.placements.filter((placement)=>placement.module.category==='corridor');
      const servedRooms=rooms.filter((room)=>[...(adjacency.get(room.id)||[])].some((id)=>this.placements[id].module.category==='corridor')).length;
      let corridorLinkQuality=0;
      if(corridors.length){
        corridorLinkQuality=corridors.reduce((sum,corridor)=>{
          const neighbors=[...(adjacency.get(corridor.id)||[])];
          const useful=neighbors.filter((id)=>['room','core'].includes(this.placements[id].module.category));
          const interior=corridor.cells.every((cell)=>(this.site.outerDistance.get(G.key(cell.x,cell.y))??999)>0)?1:0;
          return sum+.5*G.clamp(useful.length/2,0,1)+.25*(neighbors.length>=2?1:0)+.25*interior;
        },0)/corridors.length;
      }
      const circulationQuality=this.settings.singleFloor?1:.7*corridorLinkQuality+.3*(rooms.length?servedRooms/rooms.length:0);
      const angles=this.placements.map((placement)=>(placement.rotation||0)%180);
      let orientationQuality=0,nonOrthogonality=0;
      if(angles.length){
        const vector=angles.reduce((sum,angle)=>({x:sum.x+Math.cos(2*angle*Math.PI/180),y:sum.y+Math.sin(2*angle*Math.PI/180)}),{x:0,y:0});
        const coherence=Math.hypot(vector.x,vector.y)/angles.length;
        nonOrthogonality=angles.reduce((sum,angle)=>{const r=angle%90;return sum+Math.min(r,90-r)/45;},0)/angles.length;
        orientationQuality=.55*coherence+.45*nonOrthogonality;
      }
      const nonTrivialUse=moduleCount?this.placements.filter((placement)=>!['square','3:2','compact','linear','paired','balanced'].includes(placement.module.family)).length/moduleCount:0;
      const shearUse=moduleCount?this.placements.filter((placement)=>placement.module.family==='sheared').length/moduleCount:0;
      const spatialNovelty=.5*orientationQuality+.25*nonTrivialUse+.25*G.clamp(shearUse/.18,0,1);
      let atriumUse=.7;
      if(this.site.holes.length){
        const ring=this.site.cells.filter((cell)=>(this.site.atriumDistance.get(G.key(cell.x,cell.y))??999)===0);
        const engaged=ring.filter((cell)=>this.occupied.has(G.key(cell.x,cell.y))).length;
        const corridorRing=ring.filter((cell)=>{const id=this.occupied.get(G.key(cell.x,cell.y));return id!==undefined&&this.placements[id]?.module.category==='corridor';}).length;
        atriumUse=ring.length?.65*(engaged/ring.length)+.35*G.clamp(corridorRing/Math.max(1,ring.length)*3,0,1):0;
      }
      const geometryValidation=this.validateGeometry();
      const qualities = {
        Fill: fillRatio,
        Reuse: reuse,
        Daylight: daylight,
        Buildability: constructibility,
        Compactness: compactness*connectivity,
        Regularity: regularity,
        Orientation:orientationQuality,
        Circulation:circulationQuality,
        'Atrium use':atriumUse,
        Novelty:spatialNovelty,
        'Shear use':G.clamp(shearUse/.18,0,1),
        Travel: travelQuality
      };
      const score=100*(fillRatio*.32+reuse*.11+daylight*.08+constructibility*.09+compactness*connectivity*.07+regularity*.08+orientationQuality*.07+circulationQuality*.08+atriumUse*.04+spatialNovelty*.04+travelQuality*.02);
      return {
        filledArea, siteArea, fillRatio, exposedPerimeter, envelopeEfficiency, moduleCount,
        dictionaryUsed, dictionaryLength:this.dictionary?this.dictionary.length:0, reuse, daylight,
        constructibility, compactness, connectivity, components, averageTravel, travelQuality,
        sizeRatio,regularity,orientationQuality,nonOrthogonality,spatialNovelty,shearUse,circulationQuality,atriumUse,servedRooms,
        boundaryViolations:geometryValidation.boundaryViolations,
        overlapViolations:geometryValidation.overlapViolations,
        qualities, score:G.clamp(score,0,100), outerPerimeter:this.site?this.site.outerPerimeter:0,
        innerPerimeter:this.site?this.site.innerPerimeter:0
      };
    }

    validateGeometry() {
      if (!this.placements||!this.site) return {valid:true,boundaryViolations:0,overlapViolations:0};
      let boundaryViolations=0;
      let overlapViolations=0;
      this.placements.forEach((placement)=>{
        if (!G.polygonInsideSite(placement.poly,this.site.outer,this.site.holes)) boundaryViolations+=1;
      });
      for (let i=0;i<this.placements.length;i+=1) {
        for (let j=i+1;j<this.placements.length;j+=1) {
          if (G.polygonsOverlap(this.placements[i].poly,this.placements[j].poly)) overlapViolations+=1;
        }
      }
      return {valid:boundaryViolations===0&&overlapViolations===0,boundaryViolations,overlapViolations};
    }

    finishEpisode() {
      this.done = true;
      this.metrics = this.computeMetrics();
      const normalized = this.metrics.score/100;
      const advantage = G.clamp(normalized-this.baseline,-.5,.5);
      const rate = this.settings.learningRate/Math.max(1,Math.sqrt(this.trace.length/12));
      this.trace.forEach((gradient,index) => {
        const discount = Math.pow(.997,this.trace.length-index-1);
        FEATURE_NAMES.forEach((name) => {
          this.weights[name] = G.clamp(this.weights[name] + rate*advantage*discount*gradient[name], -.8, 2.2);
        });
      });
      this.baseline = .88*this.baseline + .12*normalized;
      if (this.settings.atriumPolicy === 'agent') {
        const id = this.atriumChoice.id;
        this.atriumValues[id] = .78*this.atriumValues[id] + .22*normalized;
      }
      this.lastScore = this.metrics.score;
      this.bestScore = Math.max(this.bestScore,this.lastScore);
      this.scoreHistory.push(this.lastScore);
      if (this.scoreHistory.length>40) this.scoreHistory.shift();
      return { done:true, metrics:this.metrics, advantage, score:this.lastScore };
    }
  }

  ModularRLAgent.FEATURE_NAMES = FEATURE_NAMES;
  global.ModularRLAgent = ModularRLAgent;
})(window);
