"""Frozen best-of-four alternatives under the SAME objective and validity rules.

An archive spends extra inference compute. It is not faster learning, and its
descriptor only establishes distinctions in measured contact topology.
"""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import random
import statistics
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import torch
from graph_experiments import ResearchLearner,FeasibilityRanker
from benchmark_graph_hypotheses import run_case
from compare_graph_proposals import append


def descriptor(document):
    state=document['event']['graphState'];degree=Counter()
    nodes=[n for n in state['nodes'] if n['floor']==0]
    for e in state['edgesHoriz']:
        if e['floor']==0:degree[e['u']]+=1;degree[e['v']]+=1
    histogram=Counter(min(8,degree[n['id']]) for n in nodes)
    # Degree proportions and cycle density are rotation/numbering invariant.
    # This is a coarse topology descriptor, not proof of architectural diversity.
    n=len(nodes);edges=sum(degree.values())/2
    return tuple([round(histogram[i]/max(1,n),2) for i in range(9)]+[round(max(0,edges-n+1)/max(1,n),2)])


def main(a):
    a.output.mkdir(parents=True,exist_ok=False);(a.output/'layouts').mkdir()
    m=json.loads((a.input/'manifest.json').read_text());final=m['trainingEpisodes'];run_case.final_episode=final
    source=Path(__file__).read_text()
    manifest=dict(status='running',input=str(a.input),revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        candidatesPerSite=4,objectiveChanged=False,trained=False,sourceSha256=hashlib.sha256(source.encode()).hexdigest(),
        preregistration='Deterministic baseline plus three frozen categorical samples. Same site, shared policy weights, hard geometry checks, unchanged objective. Compare valid-adjusted outcome/fill with first candidate, total inference time, and coarse contact-topology descriptor count within0.02 outcome of best. Never count invalid layouts as alternatives.')
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2));(a.output/'source.py').write_text(source)
    rows=[json.loads(line) for line in (a.input/'episodes.jsonl').read_text().splitlines()]
    cases=[r for r in rows if r['arm']=='baseline' and r['phase']=='validation' and r['trainedEpisodes']==final]
    registry={};start=time.perf_counter();errors=0
    for case,base in enumerate(cases):
        seed=base['initializationSeed'];checkpoint=torch.load(a.input/f'baseline-{seed}-{final}.pt',weights_only=False)
        candidates=[base];descriptors={0:descriptor(json.loads((a.input/base['layoutFile']).read_text()))}
        learner=ResearchLearner(seed);learner.load_research(checkpoint['learner']);learner.inference_sampling=True
        ranker=FeasibilityRanker(seed)
        for trial in range(1,4):
            learner.rng.manual_seed(seed+trial*15485863+base['index']*101)
            row=run_case(learner,ranker,'baseline',seed,'validation',base['index']+trial*1000,
                base['siteSeed'],final,a.output,registry)
            if row.get('siteFingerprint')!=base['siteFingerprint']:raise RuntimeError('archive site mismatch')
            candidates.append(row)
            if row.get('layoutFile'):descriptors[trial]=descriptor(json.loads((a.output/row['layoutFile']).read_text()))
        errors+=sum('error' in r for r in candidates)
        best=max(range(4),key=lambda j:candidates[j].get('verifiedOutcome',-1.))
        eligible=[i for i,r in enumerate(candidates) if r.get('valid') and
            r.get('verifiedOutcome',-1.)>=candidates[best].get('verifiedOutcome',-1.)-.02]
        distinct=len({descriptors[i] for i in eligible if i in descriptors})
        result=dict(initializationSeed=seed,siteSeed=base['siteSeed'],siteFingerprint=base['siteFingerprint'],
            firstOutcome=base.get('verifiedOutcome',-1.),bestOutcome=candidates[best].get('verifiedOutcome',-1.),
            firstFill=base.get('validAdjustedFill',0.),selectedFill=candidates[best].get('validAdjustedFill',0.),
            bestIndex=best,validCandidates=sum(bool(r.get('valid')) for r in candidates),
            retainedCandidates=len(eligible),distinctCoarseDescriptors=distinct,
            totalInferenceSeconds=sum(r['elapsedSeconds'] for r in candidates),firstInferenceSeconds=base['elapsedSeconds'],
            errors=[r['error'] for r in candidates if 'error' in r])
        append(a.output/'archive.jsonl',result)
        print(json.dumps(dict(case=case+1,total=len(cases),elapsed=time.perf_counter()-start)),flush=True)
    manifest.update(status='complete',cases=len(cases),errors=errors,elapsedSeconds=time.perf_counter()-start)
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    main(p.parse_args())
