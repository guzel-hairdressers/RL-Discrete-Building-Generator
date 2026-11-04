"""L/XL graph-only training + separately timed previews; 120/floor, 4 floors.

One fixed seed is a latency smoke run, not a convergence/generalization result.
Failed previews remain in the raw results; geometry is excluded from training.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import torch
from server import ParallelTrainer


def run(output,floors=4,strategy='legacy'):
    output.mkdir(parents=True,exist_ok=False)
    sources={str(p.relative_to(ROOT)):p.read_text() for p in [ROOT/'tools/benchmark_graph_training.py',
        *[ROOT/'src'/name for name in ('server.py','typed_cell.py','graph_proxy.py','graph_dictionary.py','relative_vocabulary.py','graph_sampler.py','graph_policy.py','shared_modules.py','voronoi_realizer.py')]]}
    manifest=dict(revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        protocol=f'L/XL,120 max modules per floor,{floors} floors,seed123',pilotOnly=True,
        sourceHashes={k:hashlib.sha256(v.encode()).hexdigest() for k,v in sources.items()})
    (output/'sources.json').write_text(json.dumps(sources))
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2))
    rows=[]
    for tier in ('L','XL'):
        torch.manual_seed(123)
        settings=dict(generatorEngine='graph_voronoi',graphController='neural',graphProposalStrategy=strategy,boundaryType='rect',
            siteAreaTier=tier,parallelEnvironments=floors,maxModules=120,seed=123)
        t=ParallelTrainer(settings)
        try:
            started=time.perf_counter();t.new_site();setup=time.perf_counter()-started
            started=time.perf_counter();steps=[]
            for i in range(121):
                stamp=time.perf_counter();event=t.step(t.generation_id,t.episode);elapsed=time.perf_counter()-stamp
                steps.append(dict(step=i,seconds=elapsed,nodes=len(event['graphState']['nodes']),complete=event['type']=='episodeDone'))
                if event['type']=='episodeDone':break
            else:raise RuntimeError('episode did not terminate')
            training_seconds=time.perf_counter()-started
            torch.save(t.graph_learner.state(),output/f'{tier}-weights.pt')
            before={k:v.clone() for k,v in t.graph_learner.model.state_dict().items()}
            stamp=time.perf_counter();preview=t.evaluate(t.generation_id,t.episode);preview_seconds=time.perf_counter()-stamp
            assert all(torch.equal(v,before[k]) for k,v in t.graph_learner.model.state_dict().items())
            assert event['validation']['status']=='not_run' and event['metrics']['policyUpdateCount']==1
            row=dict(tier=tier,settings=settings,setupSeconds=setup,trainingSeconds=training_seconds,
                previewSeconds=preview_seconds,steps=steps,trainingMetrics=event['metrics'],
                trainingValidation=event['validation'],previewValidation=preview['validation'],previewMetrics=preview['metrics'],
                predictionErrors=preview['predictionErrors'],terminationReason=event.get('terminationReason'),
                dictionaryMaxTypes=event['metrics'].get('dictionaryMaxTypes'),
                independentOccurrences=len(t.last_completed_graph.module_bank.instances),
                proposalRejections=dict(t.last_completed_graph.module_bank.rejections))
            (output/f'{tier}-layout.json').write_text(json.dumps(dict(graph=event['graphState'],placements=preview['placements'])))
            rows.append(row);(output/'episodes.json').write_text(json.dumps(rows,indent=2))
            active=[s['seconds'] for s in steps if not s['complete']]
            print(json.dumps(dict(tier=tier,setupSeconds=setup,trainingSeconds=training_seconds,
                previewSeconds=preview_seconds,activeMedianSeconds=statistics.median(active),
                activeMaxSeconds=max(active),nodes=steps[-1]['nodes'],types=event['metrics']['vocabSize'],
                fill=event['metrics']['fillRatio'],previewValid=preview['validation']['valid'])),flush=True)
        finally:
            t.graph_learner.clear_episode();t.executor.shutdown(wait=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--floors',type=int,choices=(4,8),default=4)
    parser.add_argument('--strategy',choices=('legacy','continuous','vocabulary'),default='legacy')
    args=parser.parse_args();run(args.output,args.floors,args.strategy)
