"""Post-hoc audit prompted by the user's 2026-11-05 screenshot.

Keeps original geometry validity/fill intact; reports the new, stricter enclosed
gap criterion separately. Never retroactively claims it was the training reward.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from realizer_experiments import from_layout
from layout_gaps import audit_solution_gaps


def main(a):
    a.output.mkdir(parents=True,exist_ok=False)
    sources={str(p.relative_to(ROOT)):p.read_text() for p in [Path(__file__).resolve(),ROOT/'src/layout_gaps.py',ROOT/'src/realizer_experiments.py']}
    manifest=dict(status='running',postHoc=True,reason='User screenshot: unintended holes between reused modules are unacceptable.',
        inputs=list(map(str,a.input)),revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        sourceHashes={k:hashlib.sha256(v.encode()).hexdigest() for k,v in sources.items()},
        criterion='No enclosed unplanned hole over0.01m2; exclude only explicitly planned void footprints/site holes. 1e-6m diagnostic seam closing does not alter actual footprints or credited area. Exterior morphological crevices are diagnostic only.')
    (a.output/'sources.json').write_text(json.dumps(sources));(a.output/'manifest.json').write_text(json.dumps(manifest,indent=2))
    groups=defaultdict(list);start=time.perf_counter();cases=errors=0
    for folder in a.input:
        records=[json.loads(line) for line in (folder/'episodes.jsonl').read_text().splitlines()]
        final=max(r['trainedEpisodes'] for r in records)
        for r in records:
            if r['phase'] not in ('validation','speed') or r['trainedEpisodes']!=final:continue
            cases+=1;row=dict(source=str(folder),arm=r['arm'],initializationSeed=r['initializationSeed'],
                index=r['index'],siteSeed=r['siteSeed'],siteFingerprint=r.get('siteFingerprint'),geometryValid=r.get('valid',False),
                originalMeanFloorFill=r.get('actualFill'),originalValidAdjustedFill=r.get('validAdjustedFill'))
            try:
                if not r.get('layoutFile'):raise RuntimeError('no frozen layout saved')
                document=json.loads((folder/r['layoutFile']).read_text());solution=from_layout(document)
                row['gapAudit']=audit_solution_gaps(solution)
                row['geometryAndEnclosedGapCheckPass']=row['geometryValid'] and row['gapAudit']['noUnplannedEnclosedGaps']
            except Exception as exc:
                errors+=1;row['error']=f'{type(exc).__name__}: {exc}';row['geometryAndEnclosedGapCheckPass']=False
            with (a.output/'cases.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
            groups[(str(folder),r['arm'])].append(row)
        print(json.dumps(dict(source=str(folder),cases=cases,errors=errors,elapsed=time.perf_counter()-start)),flush=True)
    summary={}
    for (source,arm),rows in groups.items():
        eligible=[r for r in rows if r.get('geometryValid') and 'gapAudit' in r]
        summary.setdefault(source,{})[arm]=dict(cases=len(rows),geometryValid=sum(r['geometryValid'] for r in rows),
            geometryAndEnclosedGapCheckPass=sum(r['geometryAndEnclosedGapCheckPass'] for r in rows),
            meanUnplannedGapAreaOnGeometryValid=statistics.mean(r['gapAudit']['unplannedEnclosedGapArea'] for r in eligible) if eligible else None,
            maxUnplannedGapAreaOnGeometryValid=max((r['gapAudit']['unplannedEnclosedGapArea'] for r in eligible),default=None))
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2))
    manifest.update(status='complete',cases=cases,errors=errors,elapsedSeconds=time.perf_counter()-start)
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,nargs='+',required=True);p.add_argument('--output',type=Path,required=True)
    main(p.parse_args())
