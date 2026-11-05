"""Authoritative in-memory matched-state endgame repair; L/XL120max/floor4/8.

No polygon-export dictionary reconstruction. Frozen trained policy builds each
baseline; six graph-only repair trials include full copy/rebuild costs. Independent
geometry/gap validation follows. Failures are retained, never relaxed away.
"""
import argparse,copy,hashlib,json,math,random,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import torch,server
from graph_experiments import ResearchLearner,implicit_score,rebuild_after_pose
from graph_proxy import site_net_area
from shared_modules import validate
from compare_graph_proposals import digest


def main(a):
    a.output.mkdir(parents=True,exist_ok=False)
    paths=[Path(__file__).resolve(),*sorted((ROOT/'src').glob('*.py'))]
    sources={str(p.relative_to(ROOT)):p.read_text() for p in paths}
    m=dict(status='running',revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        sourceHashes={k:hashlib.sha256(v.encode()).hexdigest() for k,v in sources.items()},
        protocol='L/XL120maximum/floor,4/8floors,seeds123/456/789. Frozen60-episode baseline policy,unchanged exact mean per-floor objective. Six continuous endgame trials,all copy/rebuild cost included. Oracle validation separate. No learned repair.',
        input=str(a.input),authoritativeDictionary=True)
    (a.output/'manifest.json').write_text(json.dumps(m,indent=2));(a.output/'sources.json').write_text(json.dumps(sources))
    rows=[];started=time.perf_counter()
    for seed in (123,456,789):
        for floors in (4,8):
            for tier in ('L','XL'):
                t=None;row=dict(seed=seed,floors=floors,tier=tier)
                try:
                    checkpoint=torch.load(a.input/f'baseline-{seed}-60.pt',weights_only=False)
                    learner=ResearchLearner(seed);learner.load_research(checkpoint['learner']);before=digest(learner)
                    settings=dict(generatorEngine='graph_voronoi',graphController='neural',graphProposalStrategy='legacy',
                        boundaryType='rect',siteAreaTier=tier,parallelEnvironments=floors,maxModules=120,seed=seed,dictCap=10,graphMaxTypes=15)
                    torch.manual_seed(2024);random.seed(seed);t=server.ParallelTrainer(settings);t.graph_learner=learner
                    t.set_mode('inference');t.update_settings({'seed':seed});tick=time.perf_counter()
                    for _ in range(124):
                        event=t.step(t.generation_id,t.episode)
                        if event['type']=='episodeDone':break
                    else:raise RuntimeError('baseline did not complete')
                    row['baselineConstructionAndValidationSeconds']=time.perf_counter()-tick
                    graph=t.last_completed_graph
                    # A training-state copy has no cached realized floor plan.
                    for key in ('last_inference','realization_audit'):graph.__dict__.pop(key,None)
                    areas={e.index:site_net_area(e.site) for e in t.environments}
                    value=implicit_score(graph.module_bank,areas);row['scoreBefore']=value
                    filled=lambda g:sum(g.module_bank.shapes[i.prototype].area*len(i.nodes) for i in g.module_bank.instances.values())/sum(areas.values())
                    row.update(fillBefore=filled(graph),floorReferences=len(graph.nodes),baselineGeometryValid=event['validation']['valid'])
                    ids=[oid for oid,i in graph.module_bank.instances.items() if i.nodes[0].cell_type.value=='room']
                    rng=random.Random(seed+floors*101+(tier=='XL'));rng.shuffle(ids)
                    ids.sort(key=lambda oid:sum(len(graph._adj_horiz[n.node_id]) for n in graph.module_bank.instances[oid].nodes))
                    trials=[];tick=time.perf_counter()
                    for j,oid in enumerate(ids[:6]):
                        instance=graph.module_bank.instances[oid];angle=rng.uniform(-math.pi,math.pi)
                        distance=rng.uniform(.05,.35)*graph.size_prior.radius
                        position=(instance.origin[0]+distance*math.cos(angle),instance.origin[1]+distance*math.sin(angle))
                        rotation=instance.angle+(rng.uniform(-.12,.12) if j%2 else 0.)
                        stamp=time.perf_counter();candidate=rebuild_after_pose(graph,oid,position,rotation)
                        score=implicit_score(candidate.module_bank,areas) if candidate is not None else None
                        accepted=score is not None and score>value+1e-6
                        trials.append(dict(seconds=time.perf_counter()-stamp,feasible=candidate is not None,accepted=accepted,scoreBefore=value,scoreAfter=score))
                        if accepted:graph=candidate;value=score
                    row.update(repairSeconds=time.perf_counter()-tick,trials=trials,scoreAfter=value,fillAfter=filled(graph))
                    tick=time.perf_counter();audit=validate(graph.module_bank.inference(),graph.site_boundaries)
                    row.update(oracleSeconds=time.perf_counter()-tick,geometryValidAfter=audit['valid'],
                        violations=audit['violations'],unresolved=audit['unresolved'],spatialQuality=audit['spatialQuality'])
                    if before!=digest(learner):raise RuntimeError('frozen policy weights changed')
                except Exception as exc:row['error']=f'{type(exc).__name__}: {exc}'
                finally:
                    if t is not None:t.executor.shutdown(wait=True)
                rows.append(row)
                with (a.output/'cases.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
                print(json.dumps({k:row.get(k) for k in ('seed','floors','tier','floorReferences','repairSeconds','geometryValidAfter','error')}),flush=True)
    m.update(status='complete',cases=len(rows),errors=sum('error' in r for r in rows),elapsedSeconds=time.perf_counter()-started)
    (a.output/'manifest.json').write_text(json.dumps(m,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    main(p.parse_args())
