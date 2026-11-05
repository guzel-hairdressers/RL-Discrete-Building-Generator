"""Matched completed-state repair cost, including the dense L/XL cases.

Corrects the first pilot's aggregate acceptance surrogate: use the exact mean
per-floor objective. This is frozen reference search, not a learning-speed claim.
"""
import argparse,hashlib,json,math,random,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from graph_experiments import restore_dictionary,rebuild_after_pose,implicit_score
from graph_proxy import site_net_area
from realizer_experiments import from_layout
from shared_modules import validate


def main(a):
    a.output.mkdir(parents=True,exist_ok=False);start=time.perf_counter()
    sources={str(p.relative_to(ROOT)):p.read_text() for p in [Path(__file__).resolve(),ROOT/'src/graph_experiments.py',ROOT/'src/graph_proxy.py',ROOT/'src/realizer_experiments.py',ROOT/'src/shared_modules.py',ROOT/'src/layout_gaps.py']}
    m=dict(status='running',inputs=list(map(str,a.input)),sourceHashes={k:hashlib.sha256(v.encode()).hexdigest() for k,v in sources.items()},
        revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        protocol='Matched baseline completed graphs;ANY/FREE held-out and L/XL120max/floor4/8floors. Six continuous local pose trials each;accept only a higher exact mean per-floor objective;all copying/rebuilding/checking timed. No training.',
        correction='Earlier pilot repair used building-wide ratio surrogate and spent trials early. Its data remain labeled; this pass tests corrected acceptance at the expensive completed states.')
    (a.output/'sources.json').write_text(json.dumps(sources));(a.output/'manifest.json').write_text(json.dumps(m,indent=2))
    cases=errors=0
    for folder in a.input:
        rows=[json.loads(x) for x in (folder/'episodes.jsonl').read_text().splitlines()]
        final=max(r['trainedEpisodes'] for r in rows)
        for r in rows:
            if r['arm']!='baseline' or r['phase'] not in ('validation','speed') or r['trainedEpisodes']!=final:continue
            cases+=1;row=dict(source=str(folder),siteFingerprint=r['siteFingerprint'],siteSeed=r['siteSeed'],
                initializationSeed=r['initializationSeed'],sourceGeometryValid=r.get('valid'),floorReferences=r.get('floorInstances'))
            try:
                if not r.get('valid'):
                    row['skippedReason']='source geometry invalid; retained';continue
                tick=time.perf_counter();solution=from_layout(json.loads((folder/r['layoutFile']).read_text()))
                graph=restore_dictionary(solution)
                areas={f:site_net_area(dict(outer=b,holes=graph.site_holes[f])) for f,b in graph.site_boundaries.items()}
                before=implicit_score(graph.module_bank,areas);current=before
                filled=lambda g:sum(g.module_bank.shapes[i.prototype].area*len(i.nodes) for i in g.module_bank.instances.values() if i.nodes[0].cell_type.value!='void')/sum(areas.values())
                row.update(restorationSeconds=time.perf_counter()-tick,scoreBefore=before,fillBefore=filled(graph))
                rng=random.Random(r['siteSeed']+r['initializationSeed']);ids=[oid for oid,i in graph.module_bank.instances.items() if i.nodes[0].cell_type.value=='room']
                rng.shuffle(ids);ids.sort(key=lambda oid:sum(len(graph._adj_horiz[n.node_id]) for n in graph.module_bank.instances[oid].nodes))
                trials=[];tick=time.perf_counter()
                for j,oid in enumerate(ids[:6]):
                    instance=graph.module_bank.instances[oid]
                    angle=rng.uniform(-math.pi,math.pi);distance=rng.uniform(.05,.35)*graph.size_prior.radius
                    position=(instance.origin[0]+distance*math.cos(angle),instance.origin[1]+distance*math.sin(angle))
                    rotation=instance.angle+(rng.uniform(-.12,.12) if j%2 else 0.)
                    trial_start=time.perf_counter();trial=rebuild_after_pose(graph,oid,position,rotation)
                    value=implicit_score(trial.module_bank,areas) if trial is not None else None
                    accepted=value is not None and value>current+1e-6
                    trials.append(dict(occurrence=oid,feasible=trial is not None,accepted=accepted,scoreBefore=current,scoreAfter=value,seconds=time.perf_counter()-trial_start))
                    if accepted:graph=trial;current=value
                row.update(repairSeconds=time.perf_counter()-tick,trials=trials,scoreAfter=current,fillAfter=filled(graph))
                tick=time.perf_counter();audit=validate(graph.module_bank.inference(),graph.site_boundaries)
                row.update(validationSeconds=time.perf_counter()-tick,geometryValidAfter=audit['valid'],
                    gapCheckAfter=audit['spatialQuality'],violations=audit['violations'])
                if not audit['valid']:raise RuntimeError('accepted implicit state failed independent geometry audit')
            except Exception as exc:errors+=1;row['error']=f'{type(exc).__name__}: {exc}'
            finally:
                with (a.output/'cases.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
            print(json.dumps(dict(case=cases,errors=errors,elapsed=time.perf_counter()-start)),flush=True)
    m.update(status='complete',cases=cases,errors=errors,elapsedSeconds=time.perf_counter()-start)
    (a.output/'manifest.json').write_text(json.dumps(m,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,nargs='+',required=True);p.add_argument('--output',type=Path,required=True)
    main(p.parse_args())
