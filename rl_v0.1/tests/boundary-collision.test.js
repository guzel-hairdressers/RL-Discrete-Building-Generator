global.window = global;

require('../geometry.js');
require('../optimizer.js');

const assert = require('node:assert/strict');
const G = global.ModGeometry;

function rectangle(x0,y0,x1,y1) {
  return [{x:x0,y:y0},{x:x1,y:y0},{x:x1,y:y1},{x:x0,y:y1}];
}

// Regression: all four module vertices are inside the arms, but two edges cross
// the re-entrant notch. Vertex-only/raster-center validation used to accept it.
const notchedSite = [{x:0,y:0},{x:10,y:0},{x:10,y:10},{x:6,y:10},{x:6,y:4},{x:4,y:4},{x:4,y:10},{x:0,y:10}];
assert.equal(G.polygonInsideSite(rectangle(2,6,8,8),notchedSite,[]),false,'must reject a polygon crossing a concave notch');
assert.equal(G.polygonInsideSite(rectangle(0,0,4,4),notchedSite,[]),true,'must allow a module to share a site edge');

const outer = rectangle(0,0,20,20);
const atrium = rectangle(7,7,13,13);
assert.equal(G.polygonInsideSite(rectangle(6,6,9,9),outer,[atrium]),false,'must reject atrium overlap');
assert.equal(G.polygonInsideSite(rectangle(1,1,6,6),outer,[atrium]),true,'must accept clear geometry');
assert.equal(G.polygonsOverlap(rectangle(0,0,5,5),rectangle(4.8,1,8,4)),true,'must detect thin polygon overlap');
assert.equal(G.polygonsOverlap(rectangle(0,0,5,5),rectangle(5,1,8,4)),false,'shared edges are legal connections');

const baseSettings = {
  atriumPolicy:'agent', singleFloor:false, minEdge:1, maxEdge:8,
  maxEdges:8, dictCap:7, angleStep:15, maxModules:90,
  travelLimit:18, learningRate:.08, speed:30
};
const families=['rect','lshape','ushape','convex','concave','lobed','tshape','free'];
let plans = 0;
let modules = 0;
let corridors=0;
let shearedKits=0;
let shearedPlacements=0;
const firstOrientations=[];

families.forEach((boundaryType,familyIndex) => {
  for (let iteration=0;iteration<6;iteration+=1) {
    const settings={...baseSettings,boundaryType,singleFloor:iteration%2===1,angleStep:[15,10,7.5][iteration%3]};
    const agent=new global.ModularRLAgent(settings,10000+familyIndex*100+iteration);
    let guard=0;
    while (!agent.done&&guard<180) { agent.step(); guard+=1; }
    assert.equal(agent.done,true,`${boundaryType} episode did not terminate`);
    const validation=agent.validateGeometry();
    assert.deepEqual(validation,{valid:true,boundaryViolations:0,overlapViolations:0},`${boundaryType} produced invalid geometry`);
    assert.ok(agent.metrics.sizeRatio>=.2-1e-8,`${boundaryType} violated 1:5 module-area ratio`);
    assert.ok(agent.dictionary.every((module)=>module.angles.every((angle)=>angle>=40-1e-8)),`${boundaryType} has an acute module`);
    assert.ok(agent.dictionary.every((module)=>module.angles.every((angle)=>Math.abs(angle/settings.angleStep-Math.round(angle/settings.angleStep))<1e-6)),`${boundaryType} violated the angle increment`);
    assert.ok(agent.placements.every((placement)=>Math.abs(placement.rotation/settings.angleStep-Math.round(placement.rotation/settings.angleStep))<1e-6),`${boundaryType} used an invalid placement rotation`);
    agent.placements.filter((placement)=>placement.module.category==='corridor').forEach((corridor)=>{
      assert.ok(corridor.initialNeighbors.length>=1,`${boundaryType} created a disconnected corridor`);
      const exteriorShare=corridor.cells.filter((cell)=>(agent.site.outerDistance.get(`${cell.x},${cell.y}`)??999)===0).length/corridor.cells.length;
      assert.ok(exteriorShare<=.35+1e-8,`${boundaryType} placed a corridor on the exterior`);
      corridors+=1;
    });
    assert.ok(agent.metrics.atriumUse>=0&&agent.metrics.atriumUse<=1,'atrium utility must be normalized');
    if(agent.dictionary.some((module)=>module.family==='sheared'))shearedKits+=1;
    shearedPlacements+=agent.placements.filter((placement)=>placement.module.family==='sheared').length;
    if(agent.placements.length)firstOrientations.push(agent.placements[0].rotation%90);
    plans+=1;
    modules+=agent.placements.length;
  }
});

console.log(`boundary-collision: ${plans} randomized plans / ${modules} modules / 0 violations`);
assert.ok(corridors>0,'the curriculum must produce circulation connectors');
assert.ok(shearedKits>0,'sheared module families must be generated');
assert.ok(shearedPlacements>0,'the policy must actually place sheared modules');
assert.ok(firstOrientations.some((angle)=>Math.abs(angle)>1e-8),'the first module must not be forced to the orthogonal grid');
console.log(`architectural-feedback: ${corridors} topological corridors / ${shearedPlacements} sheared placements / non-orthogonal seeds verified`);

const tightSettings={...baseSettings,boundaryType:'rect',singleFloor:true,minEdge:3,maxEdge:4,maxEdges:4,dictCap:5};
const tightAgent=new global.ModularRLAgent(tightSettings,77123);
assert.ok(tightAgent.dictionary.length>0,'tight edge constraints must still produce a kit');
assert.ok(tightAgent.dictionary.every((module)=>module.edgeLengths.every((edge)=>edge>=3-1e-8&&edge<=4+1e-8)),'edge constraints must not be relaxed internally');

for(let seed=0;seed<12;seed+=1){
  const boundary=G.makeBoundary('lobed',88000+seed);
  const site=G.buildSite(boundary,[]);
  assert.ok(site.reflexVertices>=3,'deep-lobed sites need at least three re-entrant vertices');
  assert.ok(site.convexityRatio<.8,'deep-lobed sites must be substantially non-convex');
}
