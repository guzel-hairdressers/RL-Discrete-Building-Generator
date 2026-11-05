"""Paired hole-fix validation; compare actual geometry, fill, reuse and runtime.

Quality:ANY/FREE changing sites,120max/floor,4floors,3seeds,24held-out plots.
Speed:L/XL120max/floor4/8floors. No speed credit for fewer reached rooms.
"""
import argparse,hashlib,json,platform,random,statistics,subprocess,sys,time
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import torch,server
from graph_dictionary import GraphDictionary
from graph_experiments import ResearchLearner
from compare_graph_proposals import digest,independent_metrics

SETTINGS=dict(generatorEngine='graph_voronoi',graphController='neural',graphProposalStrategy='legacy',
    graphPolicyArchitecture='message_passing',siteAreaTier='ANY',boundaryType='free',parallelEnvironments=4,
    maxModules=120,autoChangeEpisodes=1,dictCap=10,graphMaxTypes=15,graphPriorRadius=4.5,
    graphMinArea=1.,graphMaxArea=80.,learningRate=.001)
INITIALIZE=GraphDictionary.__init__


def case(args,arm,seed,index,settings,registry):
    row=dict(arm=arm,seed=seed,index=index,settings=settings,mode=args.mode);t=None;start=time.perf_counter()
    def initialize(bank,graph,max_types=15):
        graph.allow_unplanned_gaps=arm=='previous'
        INITIALIZE(bank,graph,max_types)
        bank.enable_closure_proposals=arm=='closure'
    try:
        checkpoint=torch.load(args.checkpoints/f'baseline-{seed}-60.pt',weights_only=False)
        learner=ResearchLearner(seed);learner.load_research(checkpoint['learner'])
        model_before=digest(learner);updates_before=learner.updates
        torch.manual_seed(2024)
        t=server.ParallelTrainer(dict(settings,seed=123));t.graph_learner=learner;learner.invalidate()
        training=args.mode=='speed' or args.train
        t.set_mode('training' if training else 'inference')
        site_seed=(900001+101*index) if args.mode=='quality' else seed
        torch.manual_seed(site_seed);random.seed(site_seed);t.update_settings({'seed':site_seed})
        sites=[dict(outer=e.site['outer'],holes=e.site.get('holes',[])) for e in t.environments]
        fp=hashlib.sha256(json.dumps(sites,sort_keys=True).encode()).hexdigest()
        key=f'{settings["siteAreaTier"]}:{settings["parallelEnvironments"]}:{index}'
        if key in registry and registry[key]!=fp:raise RuntimeError('unpaired site fingerprint')
        if key not in registry:
            registry[key]=fp
            with (args.output/'sites.jsonl').open('a') as f:f.write(json.dumps(dict(key=key,fingerprint=fp,sites=sites))+'\n')
        row.update(siteSeed=site_seed,siteFingerprint=fp,modelBefore=model_before,setupSeconds=time.perf_counter()-start)
        tick=time.perf_counter();steps=[]
        with patch.object(GraphDictionary,'__init__',initialize):
            for step in range(124):
                stamp=time.perf_counter();event=t.step(t.generation_id,t.episode)
                steps.append(dict(step=step,seconds=time.perf_counter()-stamp,nodes=len(event['graphState']['nodes'])))
                if event['type']=='episodeDone':break
            else:raise RuntimeError('episode did not terminate')
        row['rolloutSeconds']=time.perf_counter()-tick
        if training:
            if event['validation']['status']!='not_run':raise RuntimeError('training realized geometry')
            row['trainingMetrics']=event['metrics'];row['trainingValidation']=event['validation']
            before=digest(learner);tick=time.perf_counter();event=t.evaluate(t.generation_id,t.episode)
            row['previewSeconds']=time.perf_counter()-tick
            if digest(learner)!=before:raise RuntimeError('preview changed policy')
            if learner.updates!=updates_before+1:raise RuntimeError('training did not update once')
        elif digest(learner)!=model_before:raise RuntimeError('frozen evaluation changed policy')
        audit=event['validation'];spatial=audit['spatialQuality'];bank=t.last_completed_graph.module_bank
        raw=sum(v['rawUnplannedEnclosedGapArea'] for v in spatial['perFloor'].values())
        crevice=sum(v['narrowExteriorCreviceAreaDiagnostic'] for v in spatial['perFloor'].values())
        row.update(independent_metrics(event,sites),audit=audit,geometryAndGapChecksPass=spatial['geometryAndGapChecksPass'],
            unplannedGapArea=spatial['unplannedEnclosedGapArea'],rawGapArea=raw,narrowCreviceDiagnostic=crevice,
            steps=steps,floorReferences=len(t.last_completed_graph.nodes),junctionWitnesses=sum(len(v)for v in bank.junctions.values()),
            rejections=dict(bank.rejections),modelAfter=digest(learner),updateCount=learner.updates)
        name=f'{arm}-{seed}-{index}-{settings["siteAreaTier"]}-{settings["parallelEnvironments"]}.json'
        (args.output/'layouts'/name).write_text(json.dumps(dict(sites=sites,event=event)))
        row['layoutFile']='layouts/'+name
    except Exception as exc:
        row.update(error=f'{type(exc).__name__}:{exc}',valid=False,validAdjustedFill=0.,geometryAndGapChecksPass=False)
        if t is not None:t.graph_learner.clear_episode()
    finally:
        if t is not None:t.executor.shutdown(wait=True)
    row['elapsedSeconds']=time.perf_counter()-start
    with (args.output/'episodes.jsonl').open('a') as f:f.write(json.dumps(row,allow_nan=False)+'\n')
    print(json.dumps({k:row.get(k)for k in ('arm','seed','index','floorReferences','actualFill','unplannedGapArea','rawGapArea','rolloutSeconds','error')}),flush=True)
    return row


def main(args):
    args.output.mkdir(parents=True,exist_ok=False);(args.output/'layouts').mkdir()
    paths=[Path(__file__).resolve(),ROOT/'tools/compare_graph_proposals.py',*sorted((ROOT/'src').glob('*.py'))]
    sources={str(p.relative_to(ROOT)):p.read_text() for p in paths}
    manifest=dict(status='running',mode=args.mode,training=args.train or args.mode=='speed',arms=args.arms,seeds=args.seeds,cases=args.cases,
        settings=SETTINGS,revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        sourceHashes={k:hashlib.sha256(v.encode()).hexdigest()for k,v in sources.items()},
        platform=platform.platform(),torch=str(torch.__version__),device='cpu',
        preregistration='Frozen identical trained policy and paired sites;previous/guard/guard+closure. Independent geometry and enclosed-gap checks;raw tiny gaps and exterior crevices retained;fill/reuse/types/reached size reported. Quality ANY/FREE120max/floor4floors. Speed L/XL120max/floor4/8floors with one graph-only policy update and separate audit of the exact produced graph. No empty/thinned-layout success,per-instance deformation,filler relabeling,grid presets or unequal-work speedup claims.')
    (args.output/'sources.json').write_text(json.dumps(sources));(args.output/'manifest.json').write_text(json.dumps(manifest,indent=2))
    registry={};rows=[];started=time.perf_counter()
    for seed in args.seeds:
        configurations=[(i,dict(SETTINGS,graphProposalStrategy=args.strategy))for i in range(args.cases)] if args.mode=='quality' else [(seed,dict(SETTINGS,graphProposalStrategy=args.strategy,siteAreaTier=tier,boundaryType='rect',parallelEnvironments=floors))for floors in (4,8)for tier in ('L','XL')]
        for index,settings in configurations:
            order=list(args.arms);random.Random(seed+index+settings['parallelEnvironments']).shuffle(order)
            for arm in order:rows.append(case(args,arm,seed,index,settings,registry))
    summary={}
    for arm in args.arms:
        selected=[r for r in rows if r['arm']==arm]
        good=[r for r in selected if r.get('valid')]
        summary[arm]=dict(cases=len(selected),errors=sum('error'in r for r in selected),geometryValid=len(good),
            geometryAndGapChecksPass=sum(r.get('geometryAndGapChecksPass',False)for r in selected),
            meanValidAdjustedFill=statistics.mean(r.get('validAdjustedFill',0.)for r in selected),
            meanFillOnGeometryValid=statistics.mean(r['actualFill']for r in good)if good else None,
            meanRawGapArea=statistics.mean(r.get('rawGapArea',0.)for r in good)if good else None,
            maxRawGapArea=max((r.get('rawGapArea',0.)for r in good),default=None),
            meanCreviceDiagnostic=statistics.mean(r.get('narrowCreviceDiagnostic',0.)for r in good)if good else None,
            meanRolloutSeconds=statistics.mean(r.get('rolloutSeconds',0.)for r in selected),
            meanReachedReferences=statistics.mean(r.get('floorReferences',0)for r in selected),
            meanTypes=statistics.mean(r['builtTypes']for r in good)if good else None)
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2))
    manifest.update(status='complete',elapsedSeconds=time.perf_counter()-started,completedCases=len(rows),errors=sum('error'in r for r in rows))
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--mode',choices=('quality','speed'),default='quality')
    p.add_argument('--cases',type=int,default=24);p.add_argument('--seeds',type=int,nargs='+',default=[123,456,789])
    p.add_argument('--arms',nargs='+',choices=('previous','guard','closure'),default=['previous','guard','closure'])
    p.add_argument('--checkpoints',type=Path,default=ROOT/'agent_notes/benchmarks/2026-11-05-v010-hypotheses-quality-01')
    p.add_argument('--train',action='store_true');p.add_argument('--strategy',choices=('legacy','continuous','vocabulary'),default='legacy')
    main(p.parse_args())
