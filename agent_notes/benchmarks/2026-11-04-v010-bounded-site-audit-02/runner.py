import json,sys,torch,hashlib,platform
from pathlib import Path
sys.path.insert(0,'src')
from server import ParallelTrainer
out=Path('agent_notes/benchmarks/2026-11-04-v010-bounded-site-audit-02');out.mkdir(exist_ok=False)
rows=[]
for seed in (17,83,251,619,1013,2003):
 torch.manual_seed(seed)
 settings=dict(generatorEngine='graph_voronoi',graphController='neural',siteAreaTier='ANY',boundaryType='free',parallelEnvironments=4,maxModules=120,seed=seed,autoChangeEpisodes=1)
 t=ParallelTrainer(settings)
 try:
  t.new_site()
  for i in range(122):
   event=t.step(t.generation_id,t.episode)
   if event['type']=='episodeDone':break
  else:raise RuntimeError('did not complete')
  preview=t.evaluate(t.generation_id,t.episode)
  row=dict(seed=seed,settings=settings,trainingMetrics=event['metrics'],validation=preview['validation'],predictionErrors=preview['predictionErrors'],terminationReason=event.get('terminationReason'),nodes=len(event['graphState']['nodes']))
  rows.append(row)
  (out/'results.json').write_text(json.dumps(rows,indent=2))
  (out/f'{seed}-layout.json').write_text(json.dumps(dict(graph=event['graphState'],placements=preview['placements'],boundaries=[{k:e.site.get(k) for k in ('outer','holes','area')} for e in t.environments])))
  print(seed,row['nodes'],event['metrics']['vocabSize'],preview['validation']['valid'],flush=True)
 finally:t.executor.shutdown(wait=True)
sources={str(p):p.read_text() for p in [Path('src')/n for n in ('server.py','typed_cell.py','graph_dictionary.py','graph_proxy.py','graph_sampler.py','graph_policy.py','shared_modules.py')]}
(out/'sources.json').write_text(json.dumps(sources));(out/'runner.py').write_text(Path(__file__).read_text())
(out/'manifest.json').write_text(json.dumps(dict(purpose='Six seeded ANY/FREE correctness smoke cases, not quality/convergence or timing evidence',sourceHashes={k:hashlib.sha256(v.encode()).hexdigest() for k,v in sources.items()}),indent=2))
