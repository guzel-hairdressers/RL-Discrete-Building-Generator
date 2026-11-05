"""Paired exploratory analysis. Confidence intervals do not promote a default."""
import argparse
from collections import Counter
import json
from pathlib import Path
import statistics

import numpy as np
from analyze_graph_proposals import crossed_interval


def mean(rows,key,default=0.):return statistics.mean(r.get(key,default) for r in rows) if rows else None


def add_exact_fill_analysis(folder,rows):
    """Derive additional clearly named statistics; never rewrite raw evidence.

    The original pilot's actualFill is a mean of floor ratios. UI aggregation is
    a ratio of sums. Retain both, including gross plot coverage and residential
    plot coverage, so the denominator/aggregation choice cannot hide a gain.
    """
    from shapely.geometry import Polygon
    site_areas={}
    def xy(poly):return [(p['x'],p['y']) if isinstance(p,dict) else p for p in poly]
    for line in (folder/'sites.jsonl').read_text().splitlines():
        record=json.loads(line);areas=[];gross=[]
        for site in record['sites']:
            gross.append(Polygon(xy(site['outer'])).area)
            areas.append(Polygon(xy(site['outer']),[xy(h) for h in site['holes']]).area)
        site_areas[record['fingerprint']]=(areas,gross)
    derived=[]
    for row in rows:
        if row['phase'] not in ('validation','speed') or row.get('siteFingerprint') not in site_areas:continue
        net,gross=site_areas[row['siteFingerprint']]
        audit=row.get('geometryAudit',{});floors=audit.get('perFloor',{})
        filled=sum(float(m.get('filledArea',0.)) for m in floors.values())
        residential=sum(float(m.get('rentableArea',0.)) for m in floors.values())
        row['weightedExactFill']=filled/max(1e-12,sum(net))
        row['validAdjustedWeightedFill']=row['weightedExactFill'] if row.get('valid') else 0.
        row['grossPlotFill']=filled/max(1e-12,sum(gross))
        row['residentialPlotCoverage']=residential/max(1e-12,sum(net))
        derived.append({k:row.get(k) for k in ('arm','initializationSeed','trainedEpisodes','phase','index','siteFingerprint',
            'actualFill','weightedExactFill','validAdjustedWeightedFill','grossPlotFill','residentialPlotCoverage')})
    (folder/'derived_exact_fill.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in derived))


def analyze(folder,plot=None):
    manifest=json.loads((folder/'manifest.json').read_text())
    if manifest['status']!='complete':raise ValueError('study incomplete')
    rows=[json.loads(x) for x in (folder/'episodes.jsonl').read_text().splitlines()]
    add_exact_fill_analysis(folder,rows)
    seeds=manifest['seeds'];arms=manifest['arms'];final=manifest['trainingEpisodes'];cases=manifest['evaluationCases']
    index={(r['arm'],r['initializationSeed'],r['trainedEpisodes'],r['index']):r for r in rows if r['phase']=='validation'}
    milestones=sorted({r['trainedEpisodes'] for r in rows if r['phase']=='validation'})
    common=min(sum(r['arm']==arms[0] and r['initializationSeed']==seeds[0] and r['trainedEpisodes']==m and r['phase']=='validation' for r in rows) for m in milestones)
    matrices={};times={};curves={};result=dict(pilot=manifest['pilot'],arms={},paired={},multipleComparisons='exploratory; no multiplicity correction',
        confidence='Crossed bootstrap over initialization seeds/shared sites;4000 draws;three seeds limited evidence.',defaultPromotion=False)
    for arm in arms:
        vals=[index[arm,s,final,i] for s in seeds for i in range(cases)];good=[r for r in vals if r.get('valid')]
        train=[r for r in rows if r['arm']==arm and r['phase']=='train']
        matrix=lambda field,m=final:np.array([[index[arm,s,m,i].get(field,-1. if field=='verifiedOutcome' else 0.) for i in range(cases)] for s in seeds])
        matrices[arm]=dict(outcome=matrix('verifiedOutcome'),fill=matrix('validAdjustedFill'),
            weightedFill=matrix('validAdjustedWeightedFill'),gain=matrix('verifiedOutcome')-matrix('verifiedOutcome',0))
        counters=Counter();seconds=Counter()
        for r in train:
            counters.update(r.get('experiment',{}).get('counters',{}));seconds.update(r.get('experiment',{}).get('seconds',{}))
        result['arms'][arm]=dict(valid=sum(bool(r.get('valid')) for r in vals),total=len(vals),errors=sum('error' in r for r in rows if r['arm']==arm),
            finalValidAdjustedFill=float(matrices[arm]['fill'].mean()),fillOnValid=mean(good,'actualFill'),
            finalValidAdjustedWeightedFill=float(matrices[arm]['weightedFill'].mean()),weightedFillOnValid=mean(good,'weightedExactFill'),
            meanResidentialPlotCoverage=mean(good,'residentialPlotCoverage'),
            finalOutcome=float(matrices[arm]['outcome'].mean()),meanLearningGain=float(matrices[arm]['gain'].mean()),
            perSeedLearningGain={str(s):float(matrices[arm]['gain'][j].mean()) for j,s in enumerate(seeds)},
            meanTypes=mean(good,'builtTypes'),meanIndependentRepeat=mean(good,'independentRepeatFraction'),
            meanFinalFloorReferences=mean(good,'floorInstances'),maxTypes=max(r.get('builtTypes',0) for r in vals),
            meanTrainEpisodeSeconds=mean(train,'elapsedSeconds'),meanTrainRolloutSeconds=mean(train,'rolloutSeconds'),
            meanTrainReachedReferences=mean(train,'floorInstances'),trainingCases=len(train),
            counters=dict(counters),measuredComponentSeconds=dict(seconds),
            auxiliaryTrainingSeconds=sum(r.get('auxiliaryTrainingSeconds',0.) for r in train),
            episodeTimeIsEqualWorkSpeedup=False)
        curves[arm]=np.array([[statistics.mean(index[arm,s,m,i].get('verifiedOutcome',-1.) for i in range(common)) for m in milestones] for s in seeds])
        times[arm]=np.array([[sum(r['elapsedSeconds'] for r in train if r['initializationSeed']==s and r['index']<m) for m in milestones] for s in seeds])
    for arm in arms[1:]:
        entry={}
        for key in ('outcome','fill','weightedFill','gain'):
            delta=matrices[arm][key]-matrices['baseline'][key]
            entry[key+'Difference']=float(delta.mean());entry[key+'Crossed95']=crossed_interval(delta)
        common_time=np.minimum(times[arm][:,-1],times['baseline'][:,-1]);gains=[]
        for j,s in enumerate(seeds):
            a=float(np.interp(common_time[j],times[arm][j],curves[arm][j])-curves[arm][j,0])
            b=float(np.interp(common_time[j],times['baseline'][j],curves['baseline'][j])-curves['baseline'][j,0])
            gains.append(a-b)
        entry['descriptiveCommonTimeGainBySeed']={str(s):g for s,g in zip(seeds,gains)}
        result['paired'][arm]=entry
    (folder/'analysis.json').write_text(json.dumps(result,indent=2));(folder/'analysis_runner.py').write_text(Path(__file__).read_text())
    if plot:
        import matplotlib;matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,axes=plt.subplots(2,2,figsize=(13,8),constrained_layout=True)
        labels=['Control','Boundary','Ranking','Repair','Site shape'];colors=['#426b9c','#248577','#c78933','#af5e70','#755caa']
        for arm,label,color in zip(arms,labels,colors):
            fill=np.array([[statistics.mean(index[arm,s,m,i].get('validAdjustedFill',0.) for i in range(common)) for m in milestones] for s in seeds])
            axes[0,0].plot(milestones,fill.mean(0),marker='o',color=color,label=label)
            gain=curves[arm]-curves[arm][:,0,None]
            axes[0,1].plot(times[arm].mean(0),gain.mean(0),marker='o',color=color,label=label)
        axes[0,0].set(title=f'Same {common} held-out sites at each milestone',xlabel='Training episodes',ylabel='Valid-adjusted fill')
        axes[0,0].legend(fontsize=8)
        axes[0,1].set(title='Early learning; descriptive desktop timing',xlabel='Training-only wall time (s)',ylabel='Outcome gain from own untrained policy')
        axes[0,1].axhline(0,color='#777',lw=.8)
        axes[1,0].bar(labels,[result['arms'][a]['finalValidAdjustedFill'] for a in arms],color=colors)
        axes[1,0].set(title='Final:24 held-out sites ×3 initializations',ylabel='Valid-adjusted fill')
        axes[1,1].boxplot([[r['elapsedSeconds'] for r in rows if r['arm']==a and r['phase']=='train'] for a in arms],tick_labels=labels,showfliers=False)
        axes[1,1].set(title='Unequal reached sizes — not matched throughput',ylabel='Training episode seconds')
        for ax in axes.flat:ax.grid(axis='y',alpha=.2);ax.spines[['top','right']].set_visible(False)
        fig.suptitle('Independent graph hypotheses —60-episode pilot, unchanged objective')
        fig.supxlabel('Original overlap/containment/contact checks only. Gap-free floor plates and public circulation are audited separately.',fontsize=9)
        plot.parent.mkdir(parents=True,exist_ok=True);fig.savefig(plot,dpi=160);plt.close(fig)
    return result


def speed(folder):
    m=json.loads((folder/'manifest.json').read_text());rows=[json.loads(x) for x in (folder/'episodes.jsonl').read_text().splitlines()]
    if m['status']!='complete':raise ValueError('study incomplete')
    summary={}
    for arm in m['arms']:
        summary[arm]={}
        for floors in (4,8):
            for tier in ('L','XL'):
                train=[r for r in rows if r['arm']==arm and r['phase']=='train' and r['settings']['parallelEnvironments']==floors and r['settings']['siteAreaTier']==tier]
                audit=[r for r in rows if r['arm']==arm and r['phase']=='speed' and r['settings']['parallelEnvironments']==floors and r['settings']['siteAreaTier']==tier]
                component=Counter();counters=Counter()
                for r in train:
                    component.update(r['experiment']['seconds']);counters.update(r['experiment']['counters'])
                active=[s['seconds'] for r in train for s in r['steps'] if not s['complete']]
                summary[arm][f'{tier}-{floors}']=dict(cases=len(train),meanEpisodeSeconds=mean(train,'elapsedSeconds'),meanRolloutSeconds=mean(train,'rolloutSeconds'),
                    meanReachedReferences=mean(train,'floorInstances'),meanAuditFill=mean(audit,'validAdjustedFill'),valid=sum(r.get('valid',False) for r in audit),
                    medianActiveStep=statistics.median(active) if active else None,p95ActiveStep=float(np.quantile(active,.95)) if active else None,
                    counters=dict(counters),componentSeconds=dict(component))
    result=dict(arms=summary,equalWorkSpeedupClaim=False,protocol=m['speedProtocol'],failures=[r.get('error') for r in rows if 'error'in r])
    (folder/'analysis.json').write_text(json.dumps(result,indent=2));return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);p.add_argument('--plot',type=Path);p.add_argument('--speed',action='store_true')
    a=p.parse_args();print(json.dumps(speed(a.folder) if a.speed else analyze(a.folder,a.plot),indent=2))
