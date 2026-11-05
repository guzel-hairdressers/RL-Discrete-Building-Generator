import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { useStore } from '../src/store/useStore.js';
import { moduleInventory, areaMetrics, validationLabel, number } from '../src/store/presentation.js';
let sent;
const initial=useStore.getInitialState();
globalThis.WebSocket={OPEN:1};
beforeEach(()=>{
  sent=[];
  useStore.setState({...initial,hasSite:true,connected:true,generationId:7,episode:3,
    settings:{...initial.settings,boundaryType:'free',autoChangeEpisodes:21},
    socket:{readyState:1,send:(json)=>sent.push(JSON.parse(json))}},true);
});
const event=(extra={})=>({type:'placements',generationId:7,episode:3,step:2,placements:[],
  graphState:{realized:false,nodes:[]},metrics:{fillRatio:.42},...extra});
const done=(extra={})=>event({type:'episodeDone',completedEpisode:3,nextEpisode:4,
  validation:{status:'not_run',valid:null,graphValid:true},...extra});
test('start waits for mode acknowledgement and sends exact authoritative identifiers',()=>{
  useStore.getState().startTraining();
  assert.deepEqual(sent,[{cmd:'setMode',mode:'training'}]);
  useStore.getState().handleServerEvent({type:'ack',command:'setMode',mode:'training',generationId:7,episode:3});
  assert.deepEqual(sent.at(-1),{cmd:'step',generationId:7,episode:3});
  assert.equal(useStore.getState().stepInFlight,true);
});
test('graph batches advance synchronously without render or timer gates',()=>{
  useStore.setState({trainingWanted:true,phase:'running',stepInFlight:true});
  useStore.getState().handleServerEvent(event());
  assert.deepEqual(sent,[{cmd:'step',generationId:7,episode:3}]);
});
test('pause waits for an in-flight batch before one preview, with no new step',()=>{
  useStore.setState({trainingWanted:true,phase:'running',stepInFlight:true});
  useStore.getState().pauseExecution();assert.equal(sent.length,0);
  useStore.getState().handleServerEvent(event());
  assert.deepEqual(sent,[{cmd:'evaluate',generationId:7,episode:3}]);
  useStore.getState().handleServerEvent(event({isEvaluation:true,graphState:{realized:true,nodes:[]}}));
  assert.equal(sent.length,1);assert.equal(useStore.getState().trainingWanted,false);
});
test('pause on a terminal batch previews using next server episode',()=>{
  useStore.setState({stepInFlight:true});
  useStore.getState().handleServerEvent(done());
  assert.deepEqual(sent,[{cmd:'evaluate',generationId:7,episode:4}]);
  assert.equal(useStore.getState().episode,3);
});
test('completed inference stops even when legacy autoGenerate is true and audit fails',()=>{
  useStore.setState({trainingWanted:true,phase:'running',mode:'inference',autoGenerate:true});
  useStore.getState().handleServerEvent(done({graphState:{realized:true,nodes:[]},validation:{valid:false,violations:['overlap']},placements:[{id:'actual'}]}));
  assert.equal(sent.length,0);assert.equal(useStore.getState().trainingWanted,false);
  assert.equal(useStore.getState().validation.valid,false);
  assert.deepEqual(useStore.getState().individualPlacementsList,[{id:'actual'}]);
  assert.equal(useStore.getState().episodeRecords[0].valid,false);
});
test('old-generation and old-episode placements cannot replace a current layout',()=>{
  const current={id:'current'};useStore.setState({graphState:current});
  useStore.getState().handleServerEvent(event({generationId:6}));
  useStore.getState().handleServerEvent(event({episode:2}));
  assert.equal(useStore.getState().graphState,current);assert.equal(sent.length,0);
});
test('settings apply once and consume authoritative site settings',()=>{
  useStore.getState().updateSettings({dictCap:12});
  assert.equal(useStore.getState().settings.dictCap,10);
  assert.equal(useStore.getState().pendingSite,true);
  useStore.getState().handleServerEvent(event());assert.equal(useStore.getState().step,0);
  useStore.getState().handleServerEvent({type:'ack',command:'updateSettings',generationId:8});
  assert.equal(useStore.getState().pendingSite,true);
  useStore.getState().handleServerEvent({type:'site',generationId:8,episode:3,boundaries:[],settings:{dictCap:11}});
  assert.equal(useStore.getState().settings.dictCap,11);
  assert.equal(useStore.getState().pendingSite,false);
  assert.deepEqual(sent,[{cmd:'updateSettings',settings:{dictCap:12}}]);
});
test('terminal timings stay unavailable if server did not measure them',()=>{
  useStore.setState({mode:'inference'});useStore.getState().handleServerEvent(done());
  assert.equal(useStore.getState().diagnostics.episodeTimeMs,null);
  assert.equal(useStore.getState().metrics.episodeExecutionTimeMs,undefined);
});
test('geometry previews retain estimate history and prediction differences',()=>{
  useStore.setState({mode:'inference'});useStore.getState().handleServerEvent(done());
  useStore.getState().handleServerEvent(event({isEvaluation:true,graphState:{realized:true,nodes:[]},metrics:{fillRatio:.3},predictionErrors:{0:{filledArea:4}}}));
  assert.equal(useStore.getState().episodeRecords.length,1);
  assert.equal(useStore.getState().episodeRecords[0].fill,.42);
  assert.equal(useStore.getState().predictionErrors[0].filledArea,4);
});
test('errors stop execution instead of an unbounded retry loop',()=>{
  useStore.setState({trainingWanted:true});useStore.getState().handleServerEvent({type:'error',message:'invalid configuration'});
  assert.equal(sent.length,0);assert.equal(useStore.getState().trainingWanted,false);
});
test('palette counts occurrence IDs separately from floor references and functions',()=>{
  const rows=moduleInventory([
    {id:'a',moduleId:'m',occurrenceId:'a',type:'core'},
    {id:'b',moduleId:'m',occurrenceId:'a',type:'core'},
    {id:'c',moduleId:'m',occurrenceId:'c',type:'room'},
    {id:'h',moduleId:'hole',occurrenceId:'h',type:'void'},
  ]);
  assert.equal(rows.length,1);assert.equal(rows[0].independent,2);assert.equal(rows[0].copies,1);
  assert.deepEqual([...rows[0].functions],['core','room']);
  assert.equal(moduleInventory([{id:'looks_like_floor_copy',moduleId:'m',type:'room'}])[0].independent,null);
});
test('unavailable values remain unknown and area is summed only from complete measurements',()=>{
  assert.equal(number(null),null);assert.equal(number('12.5'),12.5);
  assert.deepEqual(areaMetrics({perSite:[{filledArea:2,rentableArea:1},{filledArea:3}]}),{filled:5,residential:null,circulation:null});
  assert.equal(validationLabel({valid:null}),'Geometry not checked');
});
test('completed preview keeps inspected episode separate from the next server episode',()=>{
  useStore.setState({mode:'inference'});useStore.getState().handleServerEvent(done());
  useStore.getState().handleServerEvent(event({isEvaluation:true,episode:4,graphState:{realized:true,isComplete:true,nodes:[]}}));
  assert.equal(useStore.getState().episode,3);assert.equal(useStore.getState().nextEpisode,4);
});
test('late mode acknowledgement cannot resume paused execution',()=>{
  useStore.getState().startTraining();useStore.getState().pauseExecution();
  sent=[];useStore.getState().handleServerEvent({type:'ack',command:'setMode',mode:'training',generationId:7,episode:3});
  assert.equal(sent.length,0);assert.equal(useStore.getState().trainingWanted,false);
});
test('realized area fallbacks use audited fill and measured residential placements',()=>{
  assert.deepEqual(areaMetrics({}, {perFloor:{0:{filledArea:50},1:{filledArea:25}}},[{category:'room',area:30},{category:'core',area:45}]),{filled:75,residential:30,circulation:null});
});
test('graph realization uses physical occurrences instead of legacy merged geometry',()=>{
  useStore.setState({mode:'inference'});
  useStore.getState().handleServerEvent(done({graphState:{realized:true,nodes:[]},placements:[{id:'physical',floor:0}],mergedPlacements:[{id:'legacy'}]}));
  assert.deepEqual(useStore.getState().currentMergedPlacements,[{id:'physical',floor:0}]);
});
test('native graph geometry translates once while legacy display records keep world coordinates',async()=>{
  const { displayPolygon }=await import('../src/store/presentation.js');
  const boundaries=[{offset:{x:100,y:-50}}],poly=[{x:1,y:2},{x:3,y:4}];
  assert.deepEqual(displayPolygon({floor:0,position:{x:0,y:0},poly},boundaries),[{x:101,y:-48},{x:103,y:-46}]);
  assert.equal(displayPolygon({instanceIdx:0,poly},boundaries),poly);
});
test('reset dispatch is verified against a simulated socket without resetting live weights',()=>{
  useStore.setState({resetConfirmOpen:true});
  useStore.getState().resetPolicy();
  assert.deepEqual(sent,[{cmd:'resetPolicy'}]);
  assert.equal(useStore.getState().resetConfirmOpen,false);
  assert.equal(useStore.getState().pendingSite,true);
});

test('active wall time freezes on pause and resumes without paused or preview time',()=>{
  const original=globalThis.performance;let now=100;
  Object.defineProperty(globalThis,'performance',{configurable:true,value:{now:()=>now}});
  try {
    useStore.getState().startTraining();
    useStore.getState().handleServerEvent({type:'ack',command:'setMode',mode:'training',generationId:7,episode:3});
    now=1100;useStore.getState().pauseExecution();
    assert.equal(useStore.getState().elapsedEpisodeMs(),1000);
    now=61100;
    useStore.getState().handleServerEvent(event({step:2}));
    useStore.getState().handleServerEvent(event({isEvaluation:true,graphState:{realized:true,nodes:[]},validation:{valid:true}}));
    assert.equal(useStore.getState().elapsedEpisodeMs(),1000);
    useStore.getState().startTraining();
    useStore.getState().handleServerEvent({type:'ack',command:'setMode',mode:'training',generationId:7,episode:3});
    now=63100;useStore.setState({mode:'inference'});
    useStore.getState().handleServerEvent(done());
    assert.equal(useStore.getState().episodeRecords.at(-1).wallMs,3000);
    now=90000;assert.equal(useStore.getState().elapsedEpisodeMs(),3000);
  } finally {Object.defineProperty(globalThis,'performance',{configurable:true,value:original});}
});

test('livable facade proxy and spatial failure retain their own provenance',()=>{
  useStore.setState({mode:'inference'});
  useStore.getState().handleServerEvent(done({metrics:{daylightAccessProxy:.4,spatialRequirementsMet:false},validation:{valid:true,residentialSpatial:{requirementsMet:false}}}));
  assert.equal(useStore.getState().episodeRecords[0].exposure,.4);
  assert.equal(useStore.getState().episodeRecords[0].spatialRequirementsMet,false);
  assert.equal(validationLabel(useStore.getState().validation),'Spatial proxy requirements unmet');
  assert.equal(validationLabel({valid:false,residentialSpatial:{requirementsMet:false}}),'Validation failed');
});
