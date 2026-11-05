"""Spatial-proxy correctness/latency pilot. No convergence/speedup assumption.

Speed:L/XL120maximum/floor4/8floors. Quality:ANY/FREE changing sites.
All failures, raw metrics, exact settings, model digests and source hashes retained.
"""
import argparse,hashlib,json,math,random,statistics,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import torch,server
from graph_spatial import DEFAULTS,evidence
from graph_policy import GraphLearner

SETTINGS=dict(generatorEngine='graph_voronoi',graphController='neural',graphProposalStrategy='legacy',
    graphPolicyArchitecture='message_passing',siteAreaTier='ANY',boundaryType='free',parallelEnvironments=4,
    maxModules=120,autoChangeEpisodes=1,dictCap=10,graphMaxTypes=15,seed=123)

def digest(learner):
    h=hashlib.sha256()
    for name,value in learner.model.state_dict().items():h.update(name.encode());h.update(value.detach().cpu().numpy().tobytes())
    return h.hexdigest()

def run(args):
    SETTINGS['graphPlotDirections']=args.directions=='on'
    args.output.mkdir(parents=True,exist_ok=False);(args.output/'layouts').mkdir()
    if args.train:server.OUTPUT_DIR=str((args.output/'checkpoints').resolve())
    sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'src').glob('*.py')}
    manifest=dict(status='running',purpose='paired finite correctness/latency pilot, not convergence evidence',mode=args.mode,
        revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),sourceHashes=sources,
        settings=SETTINGS,spatialDefaults=DEFAULTS,seeds=args.seeds,cases=args.cases,arms=args.arms,device='cpu')
    snapshot={name:(ROOT/name).read_text() for name in sources}
    snapshot['tools/benchmark_graph_spatial.py']=Path(__file__).read_text()
    (args.output/'sources.json').write_text(json.dumps(snapshot))
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2));rows=[]
    for seed in args.seeds:
        learners={arm:GraphLearner(seed=seed) for arm in args.arms}
        configs=[dict(siteAreaTier=tier,boundaryType='rect',parallelEnvironments=floors) for floors in (4,8) for tier in ('L','XL')] if args.mode=='speed' else [dict(siteAreaTier='ANY',boundaryType='free',parallelEnvironments=4) for _ in range(args.cases)]
        for index,config in enumerate(configs):
            site_seed=900001+index*101 if args.mode!='speed' else seed
            arms=list(args.arms);random.Random(seed+index).shuffle(arms)
            site_hashes={}
            for arm in arms:
                settings=dict(SETTINGS,**config,graphSpatialEnabled=arm=='spatial')
                row=dict(arm=arm,seed=seed,index=index,siteSeed=site_seed,settings=settings);trainer=None
                try:
                    learner=learners[arm] if args.train else GraphLearner(seed=seed)
                    row['modelBefore']=digest(learner);before=learner.updates
                    trainer=server.ParallelTrainer(settings);trainer.graph_learner=learner
                    trainer.set_mode('training');torch.manual_seed(site_seed);random.seed(site_seed)
                    trainer.update_settings({'seed':site_seed})
                    sites=[e.site for e in trainer.environments]
                    fp=hashlib.sha256(json.dumps([dict(outer=s['outer'],holes=s.get('holes',[])) for s in sites],sort_keys=True).encode()).hexdigest()
                    site_hashes[arm]=fp;row['siteFingerprint']=fp
                    start=time.perf_counter()
                    for step in range(124):
                        event=trainer.step(trainer.generation_id,trainer.episode)
                        if event['type']=='episodeDone':break
                    else:raise RuntimeError('episode did not finish')
                    row['rolloutSeconds']=time.perf_counter()-start
                    assert event['validation']['status']=='not_run','geometry during training'
                    assert learner.updates==before+1,'missing optimizer update'
                    row['metrics']=event['metrics'];row['modelAfter']=digest(learner)
                    row['floorReferences']=len(event['graphState']['nodes']);row['updates']=learner.updates
                    # Compare exposure on every exact output, including control;
                    # measurements after training cannot influence its actions.
                    graph=trainer.last_completed_graph
                    graph.spatial_settings=dict(DEFAULTS,graphSpatialEnabled=True)
                    stamp=time.perf_counter();predicted=[evidence(graph.module_bank).metrics(f) for f in range(graph.num_floors)]
                    row['measurementSeconds']=time.perf_counter()-stamp
                    graph.spatial_settings['graphSpatialEnabled']=True
                    stamp=time.perf_counter();preview=trainer.evaluate(trainer.generation_id,trainer.episode)
                    row['previewSeconds']=time.perf_counter()-stamp
                    assert digest(learner)==row['modelAfter'],'preview changed weights'
                    audit=preview['validation'];spatial=audit.get('residentialSpatial')
                    row.update(geometryValid=audit['valid'],gapChecksPass=audit['spatialQuality']['geometryAndGapChecksPass'],
                        spatialRequirementsMet=spatial['requirementsMet'],predicted=predicted,
                        errors=spatial['predictionErrors'],actual=spatial['perFloor'])
                    name=f'{arm}-{seed}-{index}.json'
                    (args.output/'layouts'/name).write_text(json.dumps(dict(sites=[dict(outer=s['outer'],holes=s.get('holes',[])) for s in sites],event=preview)))
                    row['layoutFile']='layouts/'+name
                    if args.train and index==len(configs)-1:
                        row['checkpoint']=str(Path(trainer.save_checkpoint(f'{arm}_{seed}_{learner.updates}')).relative_to(args.output.resolve()))
                except Exception as error:
                    row['error']=f'{type(error).__name__}: {error}'
                finally:
                    if trainer:trainer.executor.shutdown(wait=True)
                rows.append(row)
                with (args.output/'episodes.jsonl').open('a') as f:f.write(json.dumps(row,allow_nan=False)+'\n')
                print(json.dumps({key:row.get(key) for key in ('arm','seed','index','floorReferences','rolloutSeconds','measurementSeconds','spatialRequirementsMet','error')}),flush=True)
            if set(args.arms)=={'baseline','spatial'}:
                assert site_hashes.get('baseline')==site_hashes.get('spatial'),'unpaired sites'
    summary={}
    for arm in ('baseline','spatial'):
        selected=[r for r in rows if r['arm']==arm];good=[r for r in selected if 'error' not in r]
        errors=[abs(v['daylightAccessProxy']) for r in good for v in r['errors'].values() if v['daylightAccessProxy'] is not None]
        summary[arm]=dict(cases=len(selected),errors=sum('error'in r for r in selected),
            geometryValid=sum(r['geometryValid'] for r in good),gapChecksPass=sum(r['gapChecksPass'] for r in good),
            spatialPass=sum(r['spatialRequirementsMet'] for r in good),
            meanRolloutSeconds=statistics.mean(r['rolloutSeconds'] for r in good) if good else None,
            meanReachedReferences=statistics.mean(r['floorReferences'] for r in good) if good else None,
            meanFill=statistics.mean(r['metrics']['fillRatio'] for r in good) if good else None,
            meanFacadeAbsoluteError=statistics.mean(errors) if errors else None,maxFacadeAbsoluteError=max(errors,default=None))
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2))
    manifest.update(status='complete',completedCases=len(rows));(args.output/'manifest.json').write_text(json.dumps(manifest,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=('quality','speed'),default='quality');p.add_argument('--cases',type=int,default=12)
    p.add_argument('--seeds',type=int,nargs='+',default=[123,456,789]);p.add_argument('--train',action='store_true');p.add_argument('--output',type=Path,required=True)
    p.add_argument('--directions',choices=('on','off'),default='on')
    p.add_argument('--arms',choices=('baseline','spatial'),nargs='+',default=['baseline','spatial'])
    run(p.parse_args())
