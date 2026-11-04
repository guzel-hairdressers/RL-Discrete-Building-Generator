"""Analyze paired frozen-geometry proposal trials; no automatic promotion."""
import argparse,json,math,statistics,random
from pathlib import Path
import numpy as np
ARMS=('legacy','continuous','vocabulary')
LABELS={'legacy':'Current proposals','continuous':'Continuous exploration','vocabulary':'Angle/length vocabulary + exploration'}

def crossed_interval(matrix,seed=20261104,repetitions=4000):
 rng=np.random.default_rng(seed);matrix=np.asarray(matrix,dtype=float)
 s,n=matrix.shape
 draws=[]
 for _ in range(repetitions):
  si=rng.integers(0,s,s);ci=rng.integers(0,n,n)
  draws.append(float(matrix[np.ix_(si,ci)].mean()))
 return [float(np.quantile(draws,.025)),float(np.quantile(draws,.975))]

def analyze(folder,plot=None):
 manifest=json.loads((folder/'manifest.json').read_text())
 rows=[json.loads(l) for l in (folder/'episodes.jsonl').read_text().splitlines()]
 seeds=manifest['seeds'];final=manifest['trainingEpisodes'];cases=manifest['evaluationCases']
 milestones=manifest['milestones'];monitor=manifest['intermediateEvaluationCases']
 index={(r['arm'],r['initializationSeed'],r['trainedEpisodes'],r['index']):r for r in rows if r['phase']=='validation'}
 summary=dict(pilot=True,completed=manifest['status']=='complete',trainingEpisodesPerArmSeed=final,
  seeds=seeds,heldOutCasesPerSeed=cases,commonLearningCurveCases=monitor,
  confidence='Crossed bootstrap over initialization seeds and shared held-out sites; 4000 draws. Three initialization seeds remain limited evidence.',arms={},paired={})
 if not summary['completed']:raise ValueError('refusing to analyze an incomplete primary run as final')
 matrices={};curves={};training_times={}
 for arm in ARMS:
  vals=[index[arm,seed,final,i] for seed in seeds for i in range(cases)]
  ini=[index[arm,seed,0,i] for seed in seeds for i in range(cases)]
  train=[r for r in rows if r['arm']==arm and r['phase']=='train']
  good=[r for r in vals if r.get('valid') and 'error' not in r]
  matrix=lambda field:np.array([[index[arm,seed,final,i].get(field,0.) for i in range(cases)] for seed in seeds])
  matrices[arm]={f:matrix(f) for f in ('verifiedOutcome','validAdjustedFill')}
  matrices[arm]['learningGain']=np.array([[index[arm,seed,final,i].get('verifiedOutcome',-1.)-index[arm,seed,0,i].get('verifiedOutcome',-1.) for i in range(cases)] for seed in seeds])
  curves[arm]=np.array([[[index[arm,seed,m,i].get('verifiedOutcome',-1.) for i in range(monitor)] for m in milestones] for seed in seeds])
  training_times[arm]=np.array([[sum(r['elapsedSeconds'] for r in train if r['initializationSeed']==seed and r['index']<m) for m in milestones] for seed in seeds])
  curve_means=curves[arm].mean(axis=-1);gains=curve_means[:,-1]-curve_means[:,0]
  thresholds={str(seed):next((m for m,y in zip(milestones,curve_means[j]) if y>=.5),None) for j,seed in enumerate(seeds)}
  stats=dict(valid=len(good),total=len(vals),errors=sum('error' in r for r in vals),
   meanOutcome=float(matrix('verifiedOutcome').mean()),initialMeanOutcome=statistics.mean(r.get('verifiedOutcome',-1.) for r in ini),
   meanValidAdjustedFill=float(matrix('validAdjustedFill').mean()),
   meanFillOnValidLayouts=statistics.mean(r['actualFill'] for r in good) if good else None,
   meanIndependentRepeatOnValidLayouts=statistics.mean(r['independentRepeatFraction'] for r in good) if good else None,
   meanTypesOnValidLayouts=statistics.mean(r['builtTypes'] for r in good) if good else None,
   maxTypes=max(r.get('builtTypes',0) for r in vals),
   meanIndependentOccurrencesOnValidLayouts=statistics.mean(r['independentOccurrences'] for r in good) if good else None,
   meanFloorInstancesOnValidLayouts=statistics.mean(r['floorInstances'] for r in good) if good else None,
   trainingCases=len(train),trainingSeconds=sum(r['elapsedSeconds'] for r in train),
   meanTrainingEpisodeSeconds=statistics.mean(r['elapsedSeconds'] for r in train),
   medianTrainingEpisodeSeconds=statistics.median(r['elapsedSeconds'] for r in train),
   meanTrainingFloorInstances=statistics.mean(r.get('floorInstances',0) for r in train),
   allHeldOutMeanGain=float(matrices[arm]['learningGain'].mean()),
   meanMonitorGain=float(gains.mean()),monitorGainBySeed={str(seed):float(gain) for seed,gain in zip(seeds,gains)},
   outcomeThreshold05FirstMilestone=thresholds,
   monitorOutcomeByMilestone={str(m):float(curve_means[:,i].mean()) for i,m in enumerate(milestones)},
   trainingSecondsByMilestone={str(m):float(training_times[arm][:,i].mean()) for i,m in enumerate(milestones)})
  selected={};factors={}
  for r in vals:
   for key,value in r.get('terminalMetrics',{}).get('selectedProposalSources',{}).items():selected[key]=selected.get(key,0)+value
   for key,value in r.get('terminalMetrics',{}).get('selectedFactorSources',{}).items():factors[key]=factors.get(key,0)+value
  stats.update(selectedProposalSources=selected,selectedFactorSources=factors)
  errors=[]
  for r in vals:
   for prediction in (r.get('predictionErrors') or {}).values():
    if 'filledArea' in prediction:errors.append(abs(float(prediction['filledArea'])))
  stats['maxAbsoluteFilledAreaPredictionError']=max(errors) if errors else None
  summary['arms'][arm]=stats
 for arm in ARMS[1:]:
  outcome=matrices[arm]['verifiedOutcome']-matrices['legacy']['verifiedOutcome']
  fill=matrices[arm]['validAdjustedFill']-matrices['legacy']['validAdjustedFill']
  learning=matrices[arm]['learningGain']-matrices['legacy']['learningGain']
  common_time=np.minimum(training_times[arm][:,-1],training_times['legacy'][:,-1])
  # Interpolate coarse milestone curves to the same training-only time budget.
  # Report as descriptive estimates, not exact episodes-to-convergence.
  average_gain=[];endpoint_gain=[]
  for j,seed in enumerate(seeds):
   x=np.linspace(0,common_time[j],101)
   a=np.interp(x,training_times[arm][j],curves[arm][j].mean(axis=-1))-curves[arm][j,0].mean()
   b=np.interp(x,training_times['legacy'][j],curves['legacy'][j].mean(axis=-1))-curves['legacy'][j,0].mean()
   average_gain.append(float(np.trapezoid(a-b,x)/max(1e-9,common_time[j])));endpoint_gain.append(float(a[-1]-b[-1]))
  summary['paired'][arm]=dict(outcomeDifference=float(outcome.mean()),outcomeCrossed95=crossed_interval(outcome),
   learningGainDifference=float(learning.mean()),learningGainCrossed95=crossed_interval(learning),
   validAdjustedFillDifference=float(fill.mean()),fillCrossed95=crossed_interval(fill),
   perSeedOutcomeDifference={str(seed):float(outcome[j].mean()) for j,seed in enumerate(seeds)},
   commonTrainingSecondsBySeed={str(seed):float(common_time[j]) for j,seed in enumerate(seeds)},
   descriptiveAverageGainDifferenceAtCommonTimeBySeed={str(seed):average_gain[j] for j,seed in enumerate(seeds)},
   descriptiveEndpointGainDifferenceAtCommonTimeBySeed={str(seed):endpoint_gain[j] for j,seed in enumerate(seeds)})
 summary['defaultPromotion']='not_performed; evaluate fill/validity/reuse, learning evidence and untouched confirmation before adoption'
 (folder/'analysis.json').write_text(json.dumps(summary,indent=2));(folder/'analysis_runner.py').write_text(Path(__file__).read_text())
 if plot:
  import matplotlib;matplotlib.use('Agg')
  import matplotlib.pyplot as plt
  fig,axes=plt.subplots(2,2,figsize=(13,8.5),constrained_layout=True)
  colors={'legacy':'#2463a8','continuous':'#d77a17','vocabulary':'#23855a'}
  for arm in ARMS:
   fills=np.array([[statistics.mean(index[arm,seed,m,i].get('validAdjustedFill',0.) for i in range(monitor)) for m in milestones] for seed in seeds])
   axes[0,0].plot(milestones,fills.mean(0),marker='o',color=colors[arm],label=LABELS[arm])
   axes[0,0].fill_between(milestones,fills.min(0),fills.max(0),color=colors[arm],alpha=.12)
   gains=curves[arm].mean(-1)-curves[arm][:,0].mean(-1)[:,None]
   axes[0,1].plot(training_times[arm].mean(0),gains.mean(0),marker='o',color=colors[arm],label=LABELS[arm])
  axes[0,0].set(title='Held-out fill: same 8 sites at every milestone',xlabel='Training episodes',ylabel='Valid-adjusted fill fraction')
  axes[0,0].legend(fontsize=8);axes[0,1].set(title='Learning gain; evaluation time excluded',xlabel='Mean training-only wall time (seconds)',ylabel='Outcome change from untrained policy');axes[0,1].axhline(0,color='#777',linewidth=.8)
  values=[summary['arms'][arm]['meanValidAdjustedFill'] for arm in ARMS]
  axes[1,0].bar(range(3),values,color=[colors[a] for a in ARMS])
  axes[1,0].set_xticks(range(3),['Current','Continuous','Vocabulary'])
  axes[1,0].set(title='Final validation: 24 sites × 3 initializations',ylabel='Valid-adjusted fill fraction')
  for i,arm in enumerate(ARMS):
   st=summary['arms'][arm];axes[1,0].text(i,values[i]+.007,f"{st['valid']}/{st['total']} valid",ha='center',fontsize=9)
  timing=[[r['elapsedSeconds'] for r in rows if r['arm']==arm and r['phase']=='train'] for arm in ARMS]
  axes[1,1].boxplot(timing,tick_labels=['Current','Continuous','Vocabulary'],showfliers=True)
  axes[1,1].set(title='Training runtime includes unequal reached layouts',ylabel='Episode wall time (seconds)')
  for ax in axes.flat:ax.grid(axis='y',alpha=.18);ax.spines[['top','right']].set_visible(False)
  fig.suptitle('Proposal comparison — 60 episodes per version and initialization',fontsize=14)
  fig.supxlabel('Shading: range across 3 initialization means. Failed geometry contributes zero fill and outcome −1.',fontsize=9)
  plot.parent.mkdir(parents=True,exist_ok=True);fig.savefig(plot,dpi=160);fig.savefig(plot.with_suffix('.svg'));plt.close(fig)
  svg=plot.with_suffix('.svg');svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
 return summary

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('folder',type=Path);p.add_argument('--plot',type=Path);a=p.parse_args()
 s=analyze(a.folder,a.plot);print(json.dumps(s,indent=2))
