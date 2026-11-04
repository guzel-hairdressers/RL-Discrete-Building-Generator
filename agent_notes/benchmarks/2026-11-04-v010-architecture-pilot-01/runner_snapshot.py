"""Controlled graph-policy quality experiments; no automatic promotion.

ANY/FREE, auto-changing sites, 120 modules/floor and four floors are fixed.
Pilot results cannot establish convergence. The full protocol uses 750 training
episodes, multiple initialization seeds and untouched confirmation sites.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import torch
import server
from graph_policy import ARCHITECTURES, GraphLearner, outcome_reward

PROTOCOL=dict(generatorEngine='graph_voronoi',graphController='neural',siteAreaTier='ANY',
    boundaryType='free',parallelEnvironments=4,maxModules=120,autoChangeEpisodes=1,
    learningRate=.001,dictCap=10,graphPriorRadius=4.5,graphMinArea=1.,graphMaxArea=80.)


def digest_model(learner):
    h=hashlib.sha256()
    for k,v in learner.model.state_dict().items():h.update(k.encode());h.update(v.detach().cpu().numpy().tobytes())
    return h.hexdigest()


def fingerprint(trainer):
    sites=[env.site.get('outer') or env.boundary.get('outer') or env.boundary.get('polygon',[]) for env in trainer.environments]
    return hashlib.sha256(json.dumps(sites,sort_keys=True).encode()).hexdigest(),sites


def measured_result(event,settings):
    """Use independent occupied union areas, not displayed graph proxy scores."""
    audit=event['validation']; placements=event.get('placements',[])
    per_floor=event['metrics'].get('perSite',[])
    # Store complete terminal metrics as evidence; canonical boundaries are stored separately.
    groups={}
    for p in placements:
        if p['category']=='void':continue
        groups.setdefault(p['moduleId'],set()).add(p.get('moduleStackId',p['id']))
    k=len(groups);independent=sum(len(v) for v in groups.values())
    singletons=sum(len(v)==1 for v in groups.values())
    budget=10.*(max(0,k-settings['dictCap'])/settings['dictCap'])**2
    singleton=5.*singletons/max(1,independent)
    return dict(valid=bool(audit['valid']),violations=audit['violations'],unresolved=audit['unresolved'],
        actualFilledArea=sum(row['filledArea'] for row in audit['perFloor'].values()),
        builtPrototypeCount=k,independentOccurrences=independent,singletonCount=singletons,
        reuseRatio=sum(len(v) for v in groups.values() if len(v)>1)/max(1,independent),
        budgetPenalty=budget,singletonPenalty=singleton,rawScore=float(event['metrics']['score']))


def verified_objective(record,sites,placements):
    from shapely.geometry import Polygon
    scores=[];fills=[]
    for f,site in enumerate(sites):
        site_points=[(p['x'],p['y']) if isinstance(p,dict) else p for p in site]
        site_area=Polygon(site_points).area
        from shapely.ops import unary_union
        built=[Polygon([(p['x'],p['y']) for p in row['poly']]) for row in placements
               if row['floor']==f and row['category']!='void']
        rooms=[Polygon([(p['x'],p['y']) for p in row['poly']]) for row in placements
               if row['floor']==f and row['category']=='room']
        filled=unary_union(built).area
        rentable=unary_union(rooms).area
        fill=filled/max(1.,site_area);fills.append(fill)
        score=80*min(1.,fill)+15*rentable/max(1.,filled)-record['budgetPenalty']-record['singletonPenalty']-35*max(0.,1-fill/.6)**2
        scores.append(score)
    raw=sum(scores)/len(scores)
    return dict(verifiedScore=raw,verifiedOutcome=outcome_reward(raw,record['valid']),
                actualFill=sum(fills)/len(fills))


def append_record(path,record):
    with path.open('a') as f:f.write(json.dumps(record,allow_nan=False)+'\n');f.flush()


def run_case(trainer,architecture,seed,phase,index,site_seed,records,site_registry,output):
    started=time.monotonic()
    learner=trainer  # Shared learned weights; a fresh environment fixes generation counters per site.
    row=dict(architecture=architecture,initializationSeed=seed,phase=phase,index=index,siteSeed=site_seed)
    torch.manual_seed(2024)
    trainer=server.ParallelTrainer(dict(PROTOCOL,seed=123,graphPolicyArchitecture=architecture))
    trainer.graph_learner=learner
    trainer.set_mode('training' if phase=='train' else 'inference')
    try:
        torch.manual_seed(site_seed);random.seed(site_seed)
        trainer.update_settings({'seed':site_seed})
        fp,sites=fingerprint(trainer)
        key=f'{"validation" if phase in ("initial_validation","validation") else phase}:{index}'
        if key in site_registry and site_registry[key]['fingerprint']!=fp:
            raise RuntimeError('site differs between architectures/seeds: comparison is not paired')
        site_registry[key]={'fingerprint':fp,'sites':sites,'siteSeed':site_seed}
        (output/'sites.json').write_text(json.dumps(site_registry,indent=2))
        before=digest_model(trainer.graph_learner)
        event=None
        for step in range(124):
            event=trainer.step(trainer.generation_id,trainer.episode)
            if step%10==0:
                print(json.dumps(dict(progress=architecture,seed=seed,phase=phase,index=index,step=step)),flush=True)
            if event['type']=='episodeDone':break
        else:raise RuntimeError('episode failed to terminate within protocol budget')
        row.update(measured_result(event,trainer.settings))
        row.update(verified_objective(row,sites,event.get('placements',[])))
        row.update(siteFingerprint=fp,modelBefore=before,modelAfter=digest_model(trainer.graph_learner),
            updateCount=trainer.graph_learner.updates,decisions=event['metrics'].get('policyDecisionCount',0),
            reward=event['metrics'].get('trainingReward'),geometryAudit=event['validation'],
            terminalMetrics=event['metrics'],steps=step+1)
        if phase!='train' and row['modelBefore']!=row['modelAfter']:
            raise RuntimeError('evaluation changed model parameters')
    except Exception as exc:
        trainer.graph_learner.clear_episode()
        row['error']=f'{type(exc).__name__}: {exc}'
    trainer.executor.shutdown(wait=True)
    row['elapsedSeconds']=time.monotonic()-started
    records.append(row);append_record(output/'episodes.jsonl',row)
    print(json.dumps({k:row.get(k) for k in ('architecture','initializationSeed','phase','index','valid','verifiedOutcome','actualFill','reuseRatio','error','elapsedSeconds')}),flush=True)
    return row


def paired_summary(records,baseline='message_passing'):
    evaluation=[r for r in records if r['phase']=='validation']
    summary={}
    for arch in sorted({r['architecture'] for r in evaluation}):
        rows=[r for r in evaluation if r['architecture']==arch]
        good=[r for r in rows if 'error' not in r]
        summary[arch]=dict(cases=len(rows),errors=len(rows)-len(good),valid=sum(r['valid'] for r in good),
            meanOutcome=sum(r['verifiedOutcome'] for r in good)/len(rows) if rows and len(rows)==len(good) else None,
            meanActualFill=sum(r['actualFill'] for r in good)/len(good) if good else None,
            meanReuse=sum(r['reuseRatio'] for r in good)/len(good) if good else None)
    initial={(r['architecture'],r['initializationSeed'],r['siteFingerprint']):r for r in records
             if r['phase']=='initial_validation' and 'error' not in r}
    for arch,stats in summary.items():
        changes=[r['verifiedOutcome']-initial[(arch,r['initializationSeed'],r['siteFingerprint'])]['verifiedOutcome']
                 for r in evaluation if r['architecture']==arch and 'error' not in r
                 and (arch,r['initializationSeed'],r['siteFingerprint']) in initial]
        stats['meanChangeFromUntrained']=sum(changes)/len(changes) if changes else None
    base={(r['initializationSeed'],r['siteFingerprint']):r for r in evaluation if r['architecture']==baseline and 'error' not in r}
    for arch in summary:
        if arch==baseline:continue
        pairs=[(r,base.get((r['initializationSeed'],r.get('siteFingerprint')))) for r in evaluation if r['architecture']==arch and 'error' not in r]
        pairs=[p for p in pairs if p[1] is not None]
        differences=[a['verifiedOutcome']-b['verifiedOutcome'] for a,b in pairs]
        rng=random.Random(20261104)
        seed_means={s:sum(a['verifiedOutcome']-b['verifiedOutcome'] for a,b in pairs if a['initializationSeed']==s)/sum(a['initializationSeed']==s for a,b in pairs)
                    for s in {a['initializationSeed'] for a,b in pairs}}
        # Hierarchical bootstrap: initialization seeds and then their held-out cases.
        draws=[]
        if differences:
            seeds=sorted(seed_means)
            for _ in range(2000):
                sample=[]
                for s in rng.choices(seeds,k=len(seeds)):
                    ds=[a['verifiedOutcome']-b['verifiedOutcome'] for a,b in pairs if a['initializationSeed']==s]
                    sample.append(sum(rng.choices(ds,k=len(ds)))/len(ds))
                draws.append(sum(sample)/len(sample))
        draws.sort()
        minimum_cases=24*3
        enough=len(pairs)>=minimum_cases and len(seed_means)>=3
        no_extra_invalid=all(sum(not a['valid'] for a,b in pairs if a['initializationSeed']==s)<=sum(not b['valid'] for a,b in pairs if a['initializationSeed']==s) for s in seed_means)
        summary[arch].update(pairedCases=len(pairs),meanPairedDifference=sum(differences)/len(differences) if differences else None,
            hierarchicalBootstrap95=[draws[49],draws[1949]] if draws else None,
            perInitializationMeanDifference=seed_means,
            validationCandidate=bool(enough and no_extra_invalid and min(seed_means.values())>0 and draws[49]>0 and not summary[arch]['errors']))
    return dict(architectures=summary,promotion='not_performed',
        minimumEvidence='3 initialization seeds, 24 validation sites each; then untouched confirmation sites',
        pilotOnly=not any(v.get('validationCandidate') for v in summary.values()))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--architectures',nargs='+',choices=ARCHITECTURES,default=list(ARCHITECTURES))
    parser.add_argument('--seeds',nargs='+',type=int,default=[123,456,789])
    parser.add_argument('--train-episodes',type=int,default=750)
    parser.add_argument('--eval-cases',type=int,default=24)
    args=parser.parse_args()
    if args.train_episodes<1 or args.eval_cases<1:parser.error('episode counts must be positive')
    args.output.mkdir(parents=True,exist_ok=True)
    if (args.output/'manifest.json').exists():parser.error('output already contains a run; choose a fresh directory')
    manifest=dict(protocol=PROTOCOL,architectures=args.architectures,seeds=args.seeds,
        trainEpisodes=args.train_episodes,evalCases=args.eval_cases,objective='graph_tanh_v1',
        revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        workingDiff=subprocess.check_output(['git','diff','--','src/graph_policy.py','src/server.py','src/shared_modules.py'],text=True),
        torchVersion=str(torch.__version__),device='cpu',status='running')
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2))
    records=[];site_registry={}
    for seed in args.seeds:
        for arch in args.architectures:
            learner=GraphLearner('cpu',seed,.001,arch)
            manifest.setdefault('parameterCounts',{})[arch]=sum(p.numel() for p in learner.model.parameters())
            (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2))
            for i in range(args.eval_cases):run_case(learner,arch,seed,'initial_validation',i,10000000+i*137,records,site_registry,args.output)
            for i in range(args.train_episodes):run_case(learner,arch,seed,'train',i,100000+i*137,records,site_registry,args.output)
            torch.save(learner.state(),args.output/f'{arch}_seed{seed}.pt')
            for i in range(args.eval_cases):run_case(learner,arch,seed,'validation',i,10000000+i*137,records,site_registry,args.output)
            (args.output/'summary.json').write_text(json.dumps(paired_summary(records),indent=2))
    manifest['status']='completed'
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2))
    (args.output/'summary.json').write_text(json.dumps(paired_summary(records),indent=2))

if __name__=='__main__':main()
