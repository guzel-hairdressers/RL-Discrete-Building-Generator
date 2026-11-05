"""Paired angle-vocabulary/continuous-policy experiment, with frozen geometry audits.

Quality: ANY/FREE, changing site each episode, four floors,120 max/floor.
This finite pilot is not a convergence claim. Every failure remains in the data.
"""
import argparse,hashlib,json,math,platform,random,statistics,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import torch
import server
from graph_policy import GraphLearner,outcome_reward

ARMS=('legacy','continuous','vocabulary')
PROTOCOL=dict(generatorEngine='graph_voronoi',graphController='neural',graphPolicyArchitecture='message_passing',
 siteAreaTier='ANY',boundaryType='free',parallelEnvironments=4,maxModules=120,autoChangeEpisodes=1,
 learningRate=.001,dictCap=10,graphMaxTypes=15,graphPriorRadius=4.5,graphMinArea=1.,graphMaxArea=80.)


def digest(learner):
 h=hashlib.sha256()
 for k,v in learner.model.state_dict().items():h.update(k.encode());h.update(v.detach().cpu().numpy().tobytes())
 return h.hexdigest()


def append(path,row):
 with path.open('a') as f:f.write(json.dumps(row,allow_nan=False)+'\n');f.flush()


def independent_metrics(event,sites):
 from shapely.geometry import Polygon
 audit=event['validation'];groups={}
 for p in event['placements']:
  if p['category']!='void':groups.setdefault(p['moduleId'],set()).add(p.get('moduleStackId',p['id']))
 n=sum(map(len,groups.values()));k=len(groups);singletons=sum(len(v)==1 for v in groups.values())
 budget=10.*(max(0,k-10)/10.)**2;singleton=5.*singletons/max(1,n);reuse_bonus=20.*(n-k)/max(1,n)
 scores=[];fills=[];area_errors=[];filled_areas=[];site_areas=[]
 for f,site in enumerate(sites):
  xy=lambda poly:[(p['x'],p['y']) if isinstance(p,dict) else p for p in poly]
  site_area=Polygon(xy(site['outer']),[xy(h) for h in site['holes']]).area
  # Certified disjoint convex interiors: sum independent polygon areas. Invalid
  # layouts keep their audit, but receive -1 outcome and zero valid-adjusted fill.
  built=[p for p in event['placements'] if p['floor']==f and p['category']!='void']
  filled=sum(Polygon(xy(p['poly'])).area for p in built)
  rentable=sum(Polygon(xy(p['poly'])).area for p in built if p['category']=='room')
  fill=filled/max(1.,site_area);fills.append(fill)
  filled_areas.append(filled);site_areas.append(site_area)
  scores.append(80*min(1.,fill)+15*rentable/max(1.,filled)+reuse_bonus-budget-singleton-35*max(0.,1-fill/.6)**2)
  area_errors.append(filled-audit.get('perFloor',{}).get(f,{}).get('filledArea',filled))
 score=statistics.mean(scores);valid=bool(audit['valid'])
 weighted_fill=math.fsum(filled_areas)/max(1.,math.fsum(site_areas))
 return dict(valid=valid,verifiedScore=score,verifiedOutcome=outcome_reward(score,valid),
  actualFill=weighted_fill,validAdjustedFill=weighted_fill if valid else 0.,
  meanFloorFill=statistics.mean(fills),fillAggregation='ratio_of_floor_area_sums',
  builtTypes=k,independentOccurrences=n,independentRepeatFraction=(n-k)/max(1,n),
  singletonCount=singletons,reuseBonus=reuse_bonus,independentAreaCheckErrors=area_errors)


def run_case(learner,arm,seed,phase,index,site_seed,trained,output,registry):
 training=phase=='train';started=time.perf_counter();row=dict(arm=arm,initializationSeed=seed,
  phase=phase,index=index,siteSeed=site_seed,trainedEpisodes=trained)
 t=None
 try:
  torch.manual_seed(2024)
  t=server.ParallelTrainer(dict(PROTOCOL,graphProposalStrategy=arm,seed=123))
  t.graph_learner=learner;t.set_mode('training' if training else 'inference')
  torch.manual_seed(site_seed);random.seed(site_seed);t.update_settings(dict(seed=site_seed))
  sites=[dict(outer=e.site['outer'],holes=e.site.get('holes',[])) for e in t.environments]
  fp=hashlib.sha256(json.dumps(sites,sort_keys=True).encode()).hexdigest()
  key=f'{"train" if training else "validation"}:{index}'
  if key in registry and registry[key]!=fp:raise RuntimeError('mismatched site fingerprint')
  if key not in registry:
   registry[key]=fp;append(output/'sites.jsonl',dict(key=key,fingerprint=fp,siteSeed=site_seed,sites=sites))
  row['siteFingerprint']=fp;row['modelBefore']=digest(learner)
  stamp=time.perf_counter()
  for step in range(124):
   event=t.step(t.generation_id,t.episode)
   if event['type']=='episodeDone':break
  else:raise RuntimeError('episode did not terminate')
  row['rolloutSeconds']=time.perf_counter()-stamp
  if training:
   if event['validation']['status']!='not_run':raise RuntimeError('training realized geometry')
   row.update(graphScore=float(event['metrics']['score']),graphValid=event['metrics'].get('graphValid'))
  else:
   row.update(independent_metrics(event,sites))
   if index==0 or not event['validation']['valid']:
    name=f'{arm}-{seed}-{trained}-{phase}-{index}.json'
    (output/'layouts'/name).write_text(json.dumps(dict(sites=sites,event=event)))
    row['layoutFile']='layouts/'+name
  row.update(modelAfter=digest(learner),updateCount=learner.updates,terminalMetrics=event['metrics'],
   geometryAudit=event['validation'],predictionErrors=event.get('predictionErrors'),terminationReason=event.get('terminationReason'),
   floorInstances=len(event['graphState']['nodes']),vocabulary=t.last_completed_graph.module_bank.vocabulary.export(),steps=step+1)
  if not training and row['modelBefore']!=row['modelAfter']:raise RuntimeError('evaluation updated weights')
 except Exception as exc:
  learner.clear_episode();row.update(error=f'{type(exc).__name__}: {exc}',valid=False,verifiedOutcome=-1.,validAdjustedFill=0.)
 finally:
  if t is not None:t.executor.shutdown(wait=True)
 row['elapsedSeconds']=time.perf_counter()-started
 append(output/'episodes.jsonl',row)
 return row


def summarize(rows):
 result={}
 for arm in ARMS:
  result[arm]={}
  for trained in sorted({r['trainedEpisodes'] for r in rows if r['phase']=='validation'}):
   values=[r for r in rows if r['arm']==arm and r['phase']=='validation' and r['trainedEpisodes']==trained]
   result[arm][str(trained)]=dict(cases=len(values),failures=sum('error' in r for r in values),
    valid=sum(bool(r.get('valid')) for r in values),meanOutcome=statistics.mean(r.get('verifiedOutcome',-1.) for r in values),
    meanValidAdjustedFill=statistics.mean(r.get('validAdjustedFill',0.) for r in values),
    perSeed={str(seed):statistics.mean(r.get('verifiedOutcome',-1.) for r in values if r['initializationSeed']==seed)
      for seed in sorted({r['initializationSeed'] for r in values})})
 return result


def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
 p.add_argument('--seeds',nargs='+',type=int,default=[123,456,789]);p.add_argument('--train-episodes',type=int,default=60)
 p.add_argument('--eval-cases',type=int,default=24);p.add_argument('--milestones',nargs='+',type=int,default=[20,40,60])
 a=p.parse_args();a.output.mkdir(exist_ok=False,parents=True);(a.output/'layouts').mkdir()
 milestones=sorted({0,a.train_episodes,*[v for v in a.milestones if 0<v<=a.train_episodes]})
 sources={str(path.relative_to(ROOT)):path.read_text() for path in [Path(__file__).resolve(),*[ROOT/'src'/name for name in
  ('server.py','graph_policy.py','graph_dictionary.py','relative_vocabulary.py','graph_sampler.py','graph_proxy.py','shared_modules.py','typed_cell.py','voronoi_realizer.py')]]}
 manifest=dict(protocol=PROTOCOL,arms=ARMS,seeds=a.seeds,trainingEpisodes=a.train_episodes,evaluationCases=a.eval_cases,
  milestones=milestones,intermediateEvaluationCases=min(8,a.eval_cases),pilot=True,status='running',
  preregistration='Same objective and network capacity; paired sites and initialization seeds; frozen independent geometry evaluation. Outcome/fill/failures/reuse versus episodes and training-only wall time. No promotion from training reward or speed caused by early stopping. Threshold mean held-out valid-adjusted outcome >= 0.5; report unreached thresholds. Confirmation required for a proposed winner.',
  revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),sourceHashes={k:hashlib.sha256(v.encode()).hexdigest() for k,v in sources.items()},
  platform=platform.platform(),python=sys.version,torch=str(torch.__version__),threads=torch.get_num_threads(),device='cpu')
 (a.output/'sources.json').write_text(json.dumps(sources));(a.output/'manifest.json').write_text(json.dumps(manifest,indent=2))
 rows=[];registry={};started=time.perf_counter()
 for seed in a.seeds:
  learners={arm:GraphLearner(seed=seed) for arm in ARMS}
  for trained in range(a.train_episodes+1):
   order=list(ARMS);random.Random(seed+trained).shuffle(order)
   if trained in milestones:
    count=a.eval_cases if trained in (0,a.train_episodes) else min(8,a.eval_cases)
    for arm in order:
     torch.save(learners[arm].state(),a.output/f'{arm}-{seed}-{trained}.pt')
     for case in range(count):rows.append(run_case(learners[arm],arm,seed,'validation',case,500003+case*101,trained,a.output,registry))
     selected=[r for r in rows if r['arm']==arm and r['initializationSeed']==seed and r['phase']=='validation' and r['trainedEpisodes']==trained]
     print(json.dumps(dict(seed=seed,arm=arm,trained=trained,evalCases=count,valid=sum(r.get('valid',False) for r in selected),
      outcome=statistics.mean(r.get('verifiedOutcome',-1.) for r in selected),elapsed=time.perf_counter()-started)),flush=True)
    (a.output/'summary.json').write_text(json.dumps(summarize(rows),indent=2))
   if trained==a.train_episodes:break
   for arm in order:
    rows.append(run_case(learners[arm],arm,seed,'train',trained,10007+trained*97,trained,a.output,registry))
   if (trained+1)%10==0:print(json.dumps(dict(seed=seed,trained=trained+1,elapsed=time.perf_counter()-started)),flush=True)
 manifest.update(status='complete',elapsedSeconds=time.perf_counter()-started)
 (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2));(a.output/'summary.json').write_text(json.dumps(summarize(rows),indent=2))

if __name__=='__main__':main()
