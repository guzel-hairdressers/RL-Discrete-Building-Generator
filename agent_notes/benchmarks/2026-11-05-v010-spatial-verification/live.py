"""Production WebSocket smoke check; no speed or convergence claim."""
import asyncio,gzip,json,time
from pathlib import Path
import websockets
OUT=Path(__file__).resolve().parent
async def main():
 async with websockets.connect('ws://127.0.0.1:8002/ws',origin='http://127.0.0.1:8002',max_size=32*1024*1024) as ws:
  async def cmd(name,**data):
   await ws.send(json.dumps(dict(cmd=name,**data)));e=json.loads(await ws.recv())
   if e['type']=='error':raise RuntimeError(e)
   return e
  await cmd('updateSettings',settings=dict(generatorEngine='graph_voronoi',boundaryType='free',siteAreaTier='L',parallelEnvironments=4,maxModules=120,seed=123,graphSpatialEnabled=True))
  site=json.loads(await ws.recv());await cmd('setMode',mode='training')
  start=time.perf_counter();generation=site['generationId'];episode=site['episode']
  for i in range(125):
   event=await cmd('step',generationId=generation,episode=episode)
   if i==0:await asyncio.sleep(2.)
   if event['type']=='episodeDone':break
  else:raise RuntimeError('did not finish')
  elapsed=time.perf_counter()-start
  assert event['validation']['status']=='not_run'
  assert event['metrics']['policyUpdateCount']==1
  assert event['metrics']['coreOccurrences']>1
  assert event['metrics']['episodeExecutionTimeMs']/1000<elapsed-1.5
  training=event
  preview=await cmd('evaluate',generationId=generation,episode=event['nextEpisode'])
  audit=preview['validation'];assert audit['valid'] and audit['spatialQuality']['geometryAndGapChecksPass']
  assert preview['metrics']['policyUpdateCount']==1
  assert audit['residentialSpatial']['environmentalComplianceVerified'] is False
  raw=sum(v['rawUnplannedEnclosedGapArea'] for v in audit['spatialQuality']['perFloor'].values());assert raw==0
  result=dict(endpoint='http://127.0.0.1:8002/',training=training,preview=preview,clientSecondsIncludingPause=elapsed,
              simulatedPauseSeconds=2.,serverActiveSeconds=training['metrics']['episodeExecutionTimeMs']/1000,rawGapArea=raw)
  (OUT/'live-event.json.gz').write_bytes(gzip.compress(json.dumps(result,allow_nan=False).encode(),mtime=0))
  summary=dict(coreOccurrences=training['metrics']['coreOccurrences'],policyUpdates=1,
    serverActiveSeconds=result['serverActiveSeconds'],clientSecondsIncludingPause=elapsed,
    geometryAndGapChecksPass=True,rawGapArea=0,spatialRequirementsMet=audit['residentialSpatial']['requirementsMet'],
    liveFacadeProxy=preview['metrics']['daylightAccessProxy'])
  (OUT/'live-summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary))
asyncio.run(main())
