"""Preregistered, paired individual graph ablations. Never promotes defaults.

Quality: ANY/FREE changing sites, 120 maximum/floor, four floors. Frozen geometry
audits are separate from training. Speed: L/XL, 120 maximum/floor, 4 AND 8 floors.
All early stops, reached sizes, rejected repairs and failed runs remain in JSONL.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import torch
import server
from graph_experiments import ARMS, GraphExperiment, ResearchLearner, FeasibilityRanker
from compare_graph_proposals import independent_metrics,digest,append

PROTOCOL=dict(generatorEngine='graph_voronoi',graphController='neural',graphPolicyArchitecture='message_passing',
    graphProposalStrategy='legacy',siteAreaTier='ANY',boundaryType='free',parallelEnvironments=4,
    maxModules=120,autoChangeEpisodes=1,learningRate=.001,dictCap=10,graphMaxTypes=15,
    graphPriorRadius=4.5,graphMinArea=1.,graphMaxArea=80.)


def run_case(learner,ranker,arm,seed,phase,index,site_seed,trained,output,registry,patch=None,audit_training=False):
    training=phase=='train';start=time.perf_counter()
    row=dict(arm=arm,initializationSeed=seed,phase=phase,index=index,siteSeed=site_seed,trainedEpisodes=trained)
    t=None;settings=dict(PROTOCOL,**(patch or {}));experiment=GraphExperiment(arm,seed=site_seed,training=training,ranker=ranker)
    try:
        torch.manual_seed(2024)
        t=server.ParallelTrainer(dict(settings,seed=123));t.graph_learner=learner
        learner.invalidate();t.graph_experiment=experiment
        t.set_mode('training' if training else 'inference')
        torch.manual_seed(site_seed);random.seed(site_seed);t.update_settings(dict(seed=site_seed))
        sites=[dict(outer=e.site['outer'],holes=e.site.get('holes',[])) for e in t.environments]
        fp=hashlib.sha256(json.dumps(sites,sort_keys=True).encode()).hexdigest()
        key=f'{phase=="train"}:{settings["siteAreaTier"]}:{settings["boundaryType"]}:{settings["parallelEnvironments"]}:{index}'
        if key in registry and registry[key]!=fp:raise RuntimeError('unpaired sites')
        if key not in registry:
            registry[key]=fp;append(output/'sites.jsonl',dict(key=key,fingerprint=fp,siteSeed=site_seed,sites=sites))
        row.update(siteFingerprint=fp,modelBefore=digest(learner),rankerUpdatesBefore=ranker.updates,
            settings=settings,setupSeconds=time.perf_counter()-start)
        steps=[];stamp=time.perf_counter()
        for step in range(124):
            tick=time.perf_counter();event=t.step(t.generation_id,t.episode)
            steps.append(dict(step=step,seconds=time.perf_counter()-tick,nodes=len(event['graphState']['nodes']),
                complete=event['type']=='episodeDone'))
            if event['type']=='episodeDone':break
        else:raise RuntimeError('episode did not terminate')
        row['rolloutSeconds']=time.perf_counter()-stamp
        tick=time.perf_counter();row['experiment']=experiment.finish();row['auxiliaryTrainingSeconds']=time.perf_counter()-tick
        if training:
            if event['validation']['status']!='not_run':raise RuntimeError('training realized geometry')
            row.update(graphScore=float(event['metrics']['score']),graphValid=event['metrics'].get('graphValid'))
        else:
            row.update(independent_metrics(event,sites))
            if trained==0 or trained==getattr(run_case,'final_episode',60) or not event['validation']['valid']:
                name=f'{arm}-{seed}-{trained}-{phase}-{index}-{settings["siteAreaTier"]}-{settings["parallelEnvironments"]}.json'
                (output/'layouts'/name).write_text(json.dumps(dict(sites=sites,event=event)))
                row['layoutFile']='layouts/'+name
        row.update(modelAfter=digest(learner),updateCount=learner.updates,rankerUpdatesAfter=ranker.updates,
            terminalMetrics=event['metrics'],geometryAudit=event['validation'],predictionErrors=event.get('predictionErrors'),
            terminationReason=event.get('terminationReason'),floorInstances=len(event['graphState']['nodes']),steps=steps,
            independentOccurrences=len(t.last_completed_graph.module_bank.instances),
            prototypeCount=len(t.last_completed_graph.module_bank.shapes))
        if not training and (row['modelBefore']!=row['modelAfter'] or ranker.updates!=row['rankerUpdatesBefore']):
            raise RuntimeError('frozen evaluation changed model')
        if audit_training:
            row['graphCaseSecondsBeforeAudit']=time.perf_counter()-start
            before=digest(learner);tick=time.perf_counter()
            preview=t.evaluate(t.generation_id,t.episode)
            row['previewSeconds']=time.perf_counter()-tick
            if digest(learner)!=before:raise RuntimeError('preview updated weights')
            name=f'{arm}-{seed}-{trained}-speed-{index}-{settings["siteAreaTier"]}-{settings["parallelEnvironments"]}.json'
            (output/'layouts'/name).write_text(json.dumps(dict(sites=sites,event=preview)))
            row['trainingAudit']=dict(independent_metrics(preview,sites),geometryAudit=preview['validation'],
                terminalMetrics=preview['metrics'],layoutFile='layouts/'+name,
                predictionErrors=preview.get('predictionErrors'))
        if phase=='speed':
            row['trainingValidation']=event['validation']
    except Exception as exc:
        learner.clear_episode();row.update(error=f'{type(exc).__name__}: {exc}',valid=False,verifiedOutcome=-1.,validAdjustedFill=0.)
    finally:
        if t is not None:t.executor.shutdown(wait=True)
    row['fullCaseWithAuditSeconds']=time.perf_counter()-start
    row['elapsedSeconds']=row.get('graphCaseSecondsBeforeAudit',row['fullCaseWithAuditSeconds'])
    append(output/'episodes.jsonl',row)
    return row


def manifest(output,mode,args):
    output.mkdir(parents=True,exist_ok=False);(output/'layouts').mkdir()
    paths=[*sorted((ROOT/'src').glob('*.py')),Path(__file__).resolve(),ROOT/'tools/compare_graph_proposals.py']
    sources={str(p.relative_to(ROOT)):p.read_text() for p in paths}
    result=dict(status='running',mode=mode,protocol=PROTOCOL,arms=args.arms,seeds=args.seeds,
        revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        sourceHashes={k:hashlib.sha256(v.encode()).hexdigest() for k,v in sources.items()},
        sourceDiff=subprocess.check_output(['git','diff','--','src','tools','tests'],text=True),
        platform=platform.platform(),python=sys.version,torch=str(torch.__version__),threads=torch.get_num_threads(),device='cpu',
        preregistration='One change per arm; equal policy capacity, control boundary inputs zero. Exact same reward and hard validity/type limits. Ranker labels training only. Repair <=6 trials/episode, reference search not learned. Frozen independent oracle, failed cases retained. No speed credit for lower fill/reached size. Report paired valid-adjusted fill/outcome, reuse, size and wall time. Pilot cannot establish convergence; no automatic promotion.',
        trainingEpisodes=args.train_episodes,evaluationCases=args.eval_cases,pilot=args.train_episodes<750,
        checkpointDirectory=str(args.checkpoint_directory) if args.checkpoint_directory else None,
        fillDefinition='occupied footprint / exact net site area;ratio of floor-area sums;mean per-floor objective scores',
        speedProtocol='L/XL,120 maximum per floor,4 and8 floors; actual reached counts reported')
    (output/'sources.json').write_text(json.dumps(sources))
    (output/'manifest.json').write_text(json.dumps(result,indent=2));return result


def quality(args):
    output=args.output;m=manifest(output,'quality',args);start=time.perf_counter();registry={};rows=[]
    run_case.final_episode=args.train_episodes
    milestones=sorted({0,args.train_episodes,*[x for x in args.milestones if 0<x<args.train_episodes]})
    for seed in args.seeds:
        learners={a:ResearchLearner(seed,boundary=a=='boundary') for a in args.arms}
        rankers={a:FeasibilityRanker(seed) for a in args.arms}
        for trained in range(args.train_episodes+1):
            order=list(args.arms);random.Random(seed+trained).shuffle(order)
            if trained in milestones:
                count=args.eval_cases if trained in (0,args.train_episodes) else min(8,args.eval_cases)
                for arm in order:
                    torch.save(dict(learner=learners[arm].state(),ranker=rankers[arm].state()),output/f'{arm}-{seed}-{trained}.pt')
                    values=[run_case(learners[arm],rankers[arm],arm,seed,'validation',i,900001+101*i,trained,output,registry) for i in range(count)]
                    print(json.dumps(dict(seed=seed,arm=arm,trained=trained,valid=sum(r.get('valid',False) for r in values),
                        fill=statistics.mean(r.get('validAdjustedFill',0.) for r in values),
                        errors=sum('error' in r for r in values),elapsed=time.perf_counter()-start)),flush=True)
                    rows.extend(values)
            if trained==args.train_episodes:break
            for arm in order:
                rows.append(run_case(learners[arm],rankers[arm],arm,seed,'train',trained,200003+97*trained,trained,output,registry))
            if (trained+1)%10==0:print(json.dumps(dict(seed=seed,trained=trained+1,elapsed=time.perf_counter()-start)),flush=True)
    m.update(status='complete',elapsedSeconds=time.perf_counter()-start,errors=sum('error' in r for r in rows),cases=len(rows))
    (output/'manifest.json').write_text(json.dumps(m,indent=2))


def speed(args):
    output=args.output;m=manifest(output,'speed',args);start=time.perf_counter();registry={};rows=[]
    # Each case trains exactly one graph episode, then audits THAT completed graph.
    # Initialization, seeds and all accepted work are reported, not normalized away.
    for seed in args.seeds:
        for floors in (4,8):
            for tier in ('L','XL'):
                order=list(args.arms);random.Random(seed+floors+(tier=='XL')).shuffle(order)
                for arm in order:
                    learner=ResearchLearner(seed,boundary=arm=='boundary');ranker=FeasibilityRanker(seed)
                    if args.checkpoint_directory:
                        source_manifest=json.loads((args.checkpoint_directory/'manifest.json').read_text())
                        checkpoint=torch.load(args.checkpoint_directory/f'{arm}-{seed}-{source_manifest["trainingEpisodes"]}.pt',weights_only=False)
                        learner.load_research(checkpoint['learner']);ranker.model.load_state_dict(checkpoint['ranker']['model'])
                        ranker.optimizer.load_state_dict(checkpoint['ranker']['optimizer']);ranker.updates=checkpoint['ranker']['updates']
                    patch=dict(siteAreaTier=tier,boundaryType='rect',parallelEnvironments=floors)
                    row=run_case(learner,ranker,arm,seed,'train',seed,seed,0,output,registry,patch,audit_training=True)
                    audit=dict(row,**row.get('trainingAudit',{}),phase='speed')
                    audit.pop('trainingAudit',None);audit['elapsedSeconds']=row.get('previewSeconds',0.)
                    append(output/'episodes.jsonl',audit)
                    rows.extend([row,audit])
                    print(json.dumps(dict(arm=arm,seed=seed,floors=floors,tier=tier,
                        seconds=row['elapsedSeconds'],nodes=row.get('floorInstances'),
                        auditValid=audit.get('valid'),errors=[r.get('error') for r in (row,audit)])),flush=True)
    m.update(status='complete',elapsedSeconds=time.perf_counter()-start,errors=sum('error' in r for r in rows),cases=len(rows))
    (output/'manifest.json').write_text(json.dumps(m,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--mode',choices=('quality','speed'),default='quality')
    p.add_argument('--arms',nargs='+',choices=ARMS,default=list(ARMS));p.add_argument('--seeds',nargs='+',type=int,default=[123,456,789])
    p.add_argument('--train-episodes',type=int,default=60);p.add_argument('--eval-cases',type=int,default=24)
    p.add_argument('--milestones',nargs='+',type=int,default=[20,40])
    p.add_argument('--checkpoint-directory',type=Path)
    a=p.parse_args();quality(a) if a.mode=='quality' else speed(a)
