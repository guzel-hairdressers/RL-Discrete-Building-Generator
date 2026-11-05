"""Smoke-check a real daemon through the production WebSocket protocol.

This is a deployment correctness check, not a speed/quality benchmark.
"""
import asyncio, json, time
from pathlib import Path
import websockets
from shapely.geometry import Polygon
from shapely.ops import unary_union

OUT = Path(__file__).resolve().parent
SETTINGS = dict(generatorEngine='graph_voronoi',graphController='neural',
    graphProposalStrategy='legacy',siteAreaTier='L',boundaryType='free',
    parallelEnvironments=9,maxModules=130,dictCap=10,graphMaxTypes=15,
    seed=123,autoChangeEpisodes=1)

async def main():
    async with websockets.connect('ws://127.0.0.1:8000/ws',max_size=32*1024*1024,
                                  origin='http://127.0.0.1:8000') as ws:
        async def command(cmd, **extra):
            await ws.send(json.dumps(dict(cmd=cmd,**extra)))
            event=json.loads(await ws.recv())
            if event['type']=='error': raise RuntimeError(event)
            return event
        ack=await command('updateSettings',settings=SETTINGS)
        assert ack['type']=='ack',ack
        site=json.loads(await ws.recv())
        (OUT/'site.json').write_text(json.dumps(site))
        await command('setMode',mode='inference')
        started=time.perf_counter()
        for step in range(140):
            event=await command('step',generationId=site['generationId'],episode=site['episode'])
            if event['type']=='episodeDone': break
        else: raise RuntimeError('generation failed to terminate')
        seconds=time.perf_counter()-started
        (OUT/'event.json').write_text(json.dumps(event))
        audit=event['validation']; spatial=audit['spatialQuality']
        rows={}
        for floor in range(9):
            polys=[Polygon([(p['x'],p['y']) for p in room['poly']])
                   for room in event['placements'] if room['floor']==floor and room['category']!='void']
            union=unary_union(polys)
            parts=[union] if union.geom_type=='Polygon' else list(union.geoms)
            rows[floor]=dict(rooms=len(polys),area=union.area,
                rawInteriorRingArea=sum(Polygon(ring).area for part in parts for ring in part.interiors))
        types={p['moduleId'] for p in event['placements'] if p['category']!='void'}
        raw=sum(row['rawUnplannedEnclosedGapArea'] for row in spatial['perFloor'].values())
        result=dict(endpoint='http://127.0.0.1:8000',settings=SETTINGS,seconds=seconds,
            geometryValid=audit['valid'],geometryAndGapChecksPass=spatial['geometryAndGapChecksPass'],
            rawGapArea=raw,moduleTypes=len(types),floorReferences=sum(r['rooms'] for r in rows.values()),
            independentPolygonUnion=rows,metrics=event['metrics'])
        (OUT/'result.json').write_text(json.dumps(result,indent=2))
        assert audit['valid'] and spatial['geometryAndGapChecksPass'] and raw==0,result
        assert 1<len(types)<=15 and all(row['rooms']>10 for row in rows.values()),result
        # Raw polygon union can contain floating-point hairline rings; retain its
        # unfiltered result independently of the server's seam-aware audit.
        print(json.dumps({k:result[k] for k in ('geometryValid','geometryAndGapChecksPass','rawGapArea','moduleTypes','floorReferences','seconds')}))

asyncio.run(main())
