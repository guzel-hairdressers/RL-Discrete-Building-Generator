global.window=global;

require('../geometry.js');
require('../optimizer.js');

const fs=require('node:fs');
const path=require('node:path');

const OUTPUT_DIR=path.resolve(__dirname,'../outputs/best-arrangements');
fs.mkdirSync(OUTPUT_DIR,{recursive:true});

const baseSettings={
  boundaryType:'lobed',atriumPolicy:'agent',singleFloor:false,
  lobeCount:5,boundaryVertices:19,concavity:.6,lobeReach:1.5,
  minEdge:1,maxEdge:8,maxEdges:8,dictCap:8,angleStep:15,
  orientationMode:'random',allowShear:true,maxModules:130,
  travelLimit:20,learningRate:.075,speed:30,edgeAlignment:true
};

function runEpisode(agent){
  let guard=0;
  while(!agent.done&&guard<220){agent.step();guard+=1;}
  if(!agent.done)agent.finishEpisode();
  return agent.metrics;
}

function snapshot(agent,variant,seed){
  return {
    variant,seed,episode:agent.episode,score:agent.metrics.score,
    orientationBasis:agent.episodeOrientation,
    boundaryFamily:agent.boundary.family,
    site:{outer:agent.site.outer,holes:agent.site.holes,exactArea:agent.site.exactArea,reflexVertices:agent.site.reflexVertices,convexityRatio:agent.site.convexityRatio},
    metrics:{...agent.metrics},
    placements:agent.placements.map((placement)=>({
      id:placement.id,poly:placement.poly,center:placement.center,rotation:placement.rotation,
      module:{id:placement.module.id,name:placement.module.name,category:placement.module.category,family:placement.module.family,area:placement.module.area}
    })),
    dictionary:agent.dictionary.map((module)=>({id:module.id,name:module.name,category:module.category,family:module.family,area:module.area,uses:module.uses,poly:module.poly}))
  };
}

function summarize(records){
  const values=records.map((record)=>record.score).sort((a,b)=>a-b);
  const mean=values.reduce((sum,value)=>sum+value,0)/values.length;
  const componentNames=['Fill','Circulation','Orientation','Atrium use','Novelty','Shear use','Regularity','Reuse','Daylight','Buildability','Compactness','Travel'];
  const components={};
  componentNames.forEach((name)=>{
    components[name]=records.reduce((sum,record)=>sum+(record.metrics.qualities[name]||0),0)/records.length;
  });
  return {count:values.length,min:values[0],mean,p50:values[Math.floor(values.length*.5)],p90:values[Math.floor(values.length*.9)],max:values[values.length-1],components};
}

const variants=[
  {name:'grid-proposals',edgeAlignment:false,sites:4,episodes:10},
  {name:'edge-heavy',edgeAlignment:true,edgeCandidateLimit:100,candidateLimit:160,sites:4,episodes:10},
  {name:'hybrid-proposals',edgeAlignment:true,edgeCandidateLimit:60,candidateLimit:190,sites:4,episodes:10},
  {name:'hybrid-search',edgeAlignment:true,edgeCandidateLimit:60,candidateLimit:190,sites:8,episodes:26}
];
const siteParameters=[
  {lobeCount:3,boundaryVertices:15,concavity:.46,lobeReach:1.3},
  {lobeCount:4,boundaryVertices:17,concavity:.52,lobeReach:1.4},
  {lobeCount:5,boundaryVertices:19,concavity:.6,lobeReach:1.5},
  {lobeCount:6,boundaryVertices:21,concavity:.64,lobeReach:1.55},
  {lobeCount:4,boundaryVertices:20,concavity:.68,lobeReach:1.5},
  {lobeCount:7,boundaryVertices:23,concavity:.58,lobeReach:1.45},
  {lobeCount:5,boundaryVertices:22,concavity:.5,lobeReach:1.35},
  {lobeCount:6,boundaryVertices:24,concavity:.7,lobeReach:1.6}
];
const allRecords=[];

variants.forEach((variant,variantIndex)=>{
  for(let siteIndex=0;siteIndex<variant.sites;siteIndex+=1){
    const seed=(variant.name==='hybrid-search'?760000:730000)+siteIndex*173;
    const agent=new global.ModularRLAgent({...baseSettings,...siteParameters[siteIndex%siteParameters.length],edgeAlignment:variant.edgeAlignment,edgeCandidateLimit:variant.edgeCandidateLimit,candidateLimit:variant.candidateLimit},seed);
    for(let episode=0;episode<variant.episodes;episode+=1){
      if(episode>=variant.episodes-4)agent.settings.greedyPolicy=true;
      runEpisode(agent);
      allRecords.push(snapshot(agent,variant.name,seed));
      if(episode<variant.episodes-1)agent.newEpisode();
    }
  }
});

const byVariant={};
variants.forEach((variant)=>{byVariant[variant.name]=summarize(allRecords.filter((record)=>record.variant===variant.name));});
const edgeRecords=allRecords.filter((record)=>record.variant!=='grid-proposals').sort((a,b)=>b.score-a.score);
const selected=[];
const usedSeeds=new Set();
for(const record of edgeRecords){
  if(usedSeeds.has(record.seed)&&selected.length<4)continue;
  selected.push(record);usedSeeds.add(record.seed);
  if(selected.length>=6)break;
}
while(selected.length<6&&edgeRecords[selected.length])selected.push(edgeRecords[selected.length]);

const report={generatedAt:new Date().toISOString(),settings:baseSettings,variants:byVariant,selected:selected.map((record,index)=>({...record,rank:index+1}))};
fs.writeFileSync(path.join(OUTPUT_DIR,'evaluation.json'),JSON.stringify(report,null,2));
console.log(JSON.stringify({variants:byVariant,selected:selected.map((record,index)=>({rank:index+1,score:Number(record.score.toFixed(2)),seed:record.seed,episode:record.episode,fill:Number((record.metrics.fillRatio*100).toFixed(1)),circulation:Number((record.metrics.circulationQuality*100).toFixed(1)),novelty:Number((record.metrics.spatialNovelty*100).toFixed(1)),modules:record.metrics.moduleCount}))},null,2));
