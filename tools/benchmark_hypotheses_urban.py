"""Untouched urban-site supplement to the ANY/FREE pilot. No training."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import torch
from shapely.geometry import Polygon
from graph_experiments import ResearchLearner,FeasibilityRanker
from benchmark_graph_hypotheses import run_case


def main(a):
    a.output.mkdir(parents=True,exist_ok=False);(a.output/'layouts').mkdir()
    quality=json.loads((a.input/'manifest.json').read_text());final=quality['trainingEpisodes'];run_case.final_episode=final
    source=ROOT/'data/real_sites_dataset.json';dataset=json.loads(source.read_text())
    selected=[];excluded=[]
    # Selection uses polygon geometry and a fixed hash, before any policy outcomes.
    # One nonrectangular plot per tier, balanced across scales. No feasibility
    # filter removes narrow/unfillable sites; such failures remain evidence.
    for tier in ('S','M','L','XL'):
        candidates=[]
        for sid,record in dataset['sites'].items():
            if record.get('area_tier')!=tier:continue
            coords=[(p['x'],p['y']) if isinstance(p,dict) else p for p in record['polygon']]
            polygon=Polygon(coords)
            if not polygon.is_valid or polygon.area<=0:
                excluded.append(dict(site=sid,reason='invalid source polygon'));continue
            rectangle=polygon.minimum_rotated_rectangle
            irregularity=1-polygon.area/max(1e-9,rectangle.area)
            if irregularity<.05:continue
            candidates.append((hashlib.sha256(('urban-holdout-20261105:'+sid).encode()).hexdigest(),sid,irregularity))
        if not candidates:raise RuntimeError('no irregular site in tier '+tier)
        _,sid,irregularity=min(candidates);record=dataset['sites'][sid]
        selected.append(dict(site=sid,tier=tier,irregularity=irregularity,polygon=record['polygon'],city=record.get('city')))
    manifest=dict(status='running',input=str(a.input),revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        sourceDatasetSha256=hashlib.sha256(source.read_bytes()).hexdigest(),selected=selected,sourceExclusions=excluded,
        sitesWereUsedForTraining=False,trained=False,selection='Fixed SHA256 order among valid source polygons >=5% smaller than their minimum oriented bounding rectangle;one per S/M/L/XL. No learned-result/feasibility filter.',
        checkpointEpisodes=final,arms=quality['arms'],seeds=quality['seeds'],limitedSupplement=True)
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2));(a.output/'source.py').write_text(Path(__file__).read_text())
    registry={};start=time.perf_counter();rows=[]
    for seed in quality['seeds']:
        for arm in quality['arms']:
            checkpoint=torch.load(a.input/f'{arm}-{seed}-{final}.pt',weights_only=False)
            learner=ResearchLearner(seed,boundary=arm=='boundary');learner.load_research(checkpoint['learner'])
            ranker=FeasibilityRanker(seed);ranker.model.load_state_dict(checkpoint['ranker']['model']);ranker.updates=checkpoint['ranker']['updates']
            for i,site in enumerate(selected):
                row=run_case(learner,ranker,arm,seed,'validation',i,780001+101*i,final,a.output,registry,
                    dict(boundaryType='real',realSiteId=site['site']))
                rows.append(row)
                print(json.dumps(dict(seed=seed,arm=arm,site=site['site'],valid=row.get('valid'),
                    fill=row.get('validAdjustedFill'),seconds=row['elapsedSeconds'],error=row.get('error'))),flush=True)
    manifest.update(status='complete',cases=len(rows),errors=sum('error' in r for r in rows),elapsedSeconds=time.perf_counter()-start)
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    main(p.parse_args())
