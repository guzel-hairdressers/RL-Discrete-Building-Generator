"""Diagnostic graph-step profiles on L/XL, 120 modules/floor, four floors.

cProfile timings include instrumentation overhead; not an episode throughput or
quality benchmark. Actual reached graph size and configuration are retained.
"""
import argparse
import cProfile
import json
from pathlib import Path
import pstats
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import torch
from server import ParallelTrainer

parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--step',type=int,default=6);args=parser.parse_args()
args.output.mkdir(parents=True,exist_ok=True)
rows=[]
for tier in ('L','XL'):
    torch.manual_seed(123)
    settings=dict(generatorEngine='graph_voronoi',graphController='neural',boundaryType='rect',
        siteAreaTier=tier,parallelEnvironments=4,maxModules=120,seed=123)
    t=ParallelTrainer(settings);t.new_site()
    print('warming',tier,flush=True)
    for i in range(args.step):
        event=t.step(t.generation_id,t.episode)
        print('warm',tier,i,len(event.get('graphState',{}).get('nodes',[])),flush=True)
        if event['type']=='episodeDone':raise RuntimeError('profile warmup ended episode; choose another seed/step')
    before=len(t.building_graph.nodes)
    profile=cProfile.Profile();started=time.perf_counter();profile.enable()
    event=t.step(t.generation_id,t.episode)
    profile.disable();wall=time.perf_counter()-started
    profile.dump_stats(str(args.output/f'{tier}.pstats'))
    stats=pstats.Stats(profile)
    functions=[]
    for (filename,line,name),(cc,nc,tt,ct,callers) in stats.stats.items():
        functions.append(dict(file=filename,line=line,function=name,primitiveCalls=cc,totalCalls=nc,
                              selfSeconds=tt,cumulativeSeconds=ct))
    functions.sort(key=lambda r:-r['cumulativeSeconds'])
    row=dict(tier=tier,settings=settings,nodesBefore=before,nodesAfter=len(event.get('graphState',{}).get('nodes',[])),
        profiledWallSeconds=wall,profileTotalSeconds=stats.total_tt,functions=functions)
    rows.append(row)
    (args.output/'profile.json').write_text(json.dumps(dict(revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        sourceDiff=subprocess.check_output(['git','diff','--','src/server.py','src/shared_modules.py','src/graph_policy.py','src/graph_sampler.py'],text=True),
        diagnosticOnly=True,rows=rows),indent=2))
    print('profiled',tier,'nodes',before,'seconds',wall,flush=True)
    for r in functions[:15]:print(r['function'],r['totalCalls'],round(r['cumulativeSeconds'],3),flush=True)
    t.graph_learner.clear_episode();t.executor.shutdown(wait=True)
