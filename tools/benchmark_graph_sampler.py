"""Matched sampler-only diagnostic on saved L/XL 480-instance graphs.

Both samplers receive the same embedded graph, boundaries and return budget.
The new sampler bounds proposal work; candidate sets need not be identical.
This measures that component, not episode throughput or learned quality.
"""
import argparse,json,statistics,subprocess,sys,time,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from server import ParallelTrainer
from typed_cell import BuildingGraph,CellType
from graph_sampler import GraphSeedSampler

def run(output):
 output.mkdir(parents=True,exist_ok=False)
 old_source=subprocess.check_output(['git','show','3e9ed018:src/graph_sampler.py'],text=True)
 namespace={'__name__':'old_sampler'};exec(compile(old_source,'old_sampler.py','exec'),namespace)
 old=namespace['GraphSeedSampler']();new=GraphSeedSampler();rows=[]
 for tier in ('L','XL'):
  fixture=ROOT/'agent_notes/benchmarks/2026-11-04-v010-graph-only-training-03'/f'{tier}-layout.json'
  data=json.loads(fixture.read_text());placements={p['node_id']:p for p in data['placements']}
  g=BuildingGraph(4)
  for n in data['graph']['nodes']:
   p=placements[n['id']]
   g.add_node(n['id'],p['position']['x'],p['position']['y'],floor_index=n['floor'],cell_type=CellType(n['type']))
  for e in data['graph']['edgesHoriz']:g.add_edge(e['u'],e['v'])
  assert len(g.nodes)==480 and all(sum(n.floor_index==f for n in g.nodes.values())==120 for f in range(4))
  t=ParallelTrainer(dict(generatorEngine='graph_voronoi',siteAreaTier=tier,boundaryType='rect',parallelEnvironments=4,maxModules=120,seed=123));t.new_site()
  timings={'old':[],'new':[]};counts={}
  for repeat in range(7):
   for name,sampler in (('old',old),('new',new)):
    started=time.perf_counter();count=0
    for f in range(4):
     boundary=t.environments[f].site['outer']
     candidates=sampler.generate_candidates(g,f,boundary,max_proposals=8)
     count+=len(candidates)
     for c in candidates:
      assert GraphSeedSampler._point_inside_polygon((c['x'],c['y']),[(p['x'],p['y']) for p in boundary],setback=1.)
      assert all((n.x-c['x'])**2+(n.y-c['y'])**2>=2.5**2-1e-8 for n in g.nodes.values() if n.floor_index==f)
    timings[name].append(time.perf_counter()-started);counts[name]=count
  rows.append(dict(tier=tier,nodes=len(g.nodes),floors=4,maxModulesPerFloor=120,proposalBudgetPerFloor=8,
   returnedCounts=counts,rawSeconds=timings,medianSeconds={k:statistics.median(v) for k,v in timings.items()},fixtureSha256=hashlib.sha256(fixture.read_bytes()).hexdigest()))
  t.executor.shutdown(wait=True)
 manifest=dict(componentOnly=True,referenceRevision='3e9ed018',oldSource=old_source,
  newSource=(ROOT/'src/graph_sampler.py').read_text(),runnerSource=Path(__file__).read_text(),rows=rows)
 (output/'results.json').write_text(json.dumps(manifest,indent=2))
 print(json.dumps([{k:r[k] for k in ('tier','nodes','returnedCounts','medianSeconds')} for r in rows]),flush=True)
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path);run(parser.parse_args().output)
