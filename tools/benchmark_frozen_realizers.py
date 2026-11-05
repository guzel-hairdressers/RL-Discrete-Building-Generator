"""Independent realization/circulation audits on frozen ANY/FREE graph layouts.

Right angles are a geometry preference, never an incident-edge graph reward.
Reference-derived wall ports are explicitly oracle inputs: this measures adapter
capability/reconstruction, not the quality of a trained port-generation policy.
"""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from graph_dictionary import rotate
from graph_proxy import SpatialNodes,root_id
from realizer_experiments import (from_layout,corner_metrics,orthogonal_completion,
    wall_evidence,realize_ports,public_circulation,xy)
from shared_modules import area,validate
from compare_graph_proposals import append


def midpoint_evidence(solution):
    graph=solution.graph;spatial=SpatialNodes(graph,solution.prior.radius)
    by_node={n.node_id:o for o in solution.occurrences.values() for n in o.nodes}
    rows={}
    for node in graph.nodes.values():
        occurrence=by_node[node.node_id]
        for other in spatial.near(node.floor_index,node.x,node.y):
            if node.node_id==other.node_id:continue
            dx,dy=other.x-node.x,other.y-node.y;distance=math.hypot(dx,dy)
            normal=rotate((dx/distance,dy/distance),-occurrence.angle)
            required=graph.has_edge(node.node_id,other.node_id)
            key=(occurrence.prototype,*[round(v,10) for v in (*normal,distance/2)])
            row=dict(prototype=occurrence.prototype,normal=normal,offset=distance/2,required=required)
            if key not in rows or required:rows[key]=row
    return list(rows.values())


def oracle_port_evidence(document):
    rows={}
    for placement in document['event']['placements']:
        origin=(placement['position']['x'],placement['position']['y']);angle=math.radians(placement['rotation'])
        local=[rotate((x-origin[0],y-origin[1]),-angle) for x,y in xy(placement['poly'])]
        for normal,bound in wall_evidence(local):
            key=(placement['moduleId'],*[round(v,10) for v in (*normal,bound)])
            if key not in rows:rows[key]=dict(prototype=placement['moduleId'],normal=normal,offset=bound,source='reference_oracle')
    return list(rows.values())


def summarize(solution,audit):
    values=[corner_metrics(p.polygon) for p in solution.prototypes.values()]
    filled=sum(row['filledArea'] for row in audit['perFloor'].values())
    residential=sum(row['rentableArea'] for row in audit['perFloor'].values())
    return dict(valid=audit['valid'],violations=audit['violations'],unresolved=audit['unresolved'],
        filledArea=filled,residentialArea=residential,
        meanPrototypeRightFraction=statistics.mean(v['weightedRightFraction'] for v in values) if values else 0.,
        meanPrototypeDeviationDegrees=statistics.mean(v['weightedDeviationDegrees'] for v in values) if values else None)


def main(args):
    output=args.output;output.mkdir(parents=True,exist_ok=False)
    files=[Path(__file__).resolve(),ROOT/'src/realizer_experiments.py',ROOT/'src/shared_modules.py']
    sources={str(p.relative_to(ROOT)):p.read_text() for p in files}
    manifest=dict(status='running',revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        sourceHashes={k:hashlib.sha256(v.encode()).hexdigest() for k,v in sources.items()},
        preregistration='Frozen baseline final held-out layouts, including failures. Compare shared orthogonal cuts at 0/2/10% maximum area loss; keep all required contacts. Reconstruct midpoint and oracle wall-port adapters with independent validation. Public corridor assignment minimum residential share65%, atomic vertical function. No learning or speedup claim from oracle ports.',
        input=str(args.input),phase=args.phase,speedClaim=False)
    (output/'sources.json').write_text(json.dumps(sources));(output/'manifest.json').write_text(json.dumps(manifest,indent=2))
    records=[json.loads(line) for line in (args.input/'episodes.jsonl').read_text().splitlines()]
    final=max(row['trainedEpisodes'] for row in records)
    selected=[r for r in records if r['arm']=='baseline' and r['phase']==args.phase and
        (r['trainedEpisodes']==final or args.phase=='speed')]
    start=time.perf_counter();errors=0
    for index,row in enumerate(selected):
        result=dict(initializationSeed=row['initializationSeed'],siteSeed=row['siteSeed'],siteFingerprint=row['siteFingerprint'])
        try:
            document=json.loads((args.input/row['layoutFile']).read_text())
            solution=from_layout(document)
            stamp=time.perf_counter();base_audit=validate(solution,solution.graph.site_boundaries)
            result['baseline']=dict(summarize(solution,base_audit),validationSeconds=time.perf_counter()-stamp)
            # Failed origins/unresolved graphs stay in the denominator. They are
            # not silently repaired by reading a pretty reference polygon.
            if not row.get('valid'):
                result['sourceInvalid']=True
            else:
                result['orthogonal']={}
                for loss in (0.,.02,.10):
                    changed,details=orthogonal_completion(solution,loss)
                    stamp=time.perf_counter();audit=validate(changed,solution.graph.site_boundaries)
                    result['orthogonal'][str(loss)]=dict(summarize(changed,audit),experiment=details,validationSeconds=time.perf_counter()-stamp)
                for name,evidence in [('midpoint',midpoint_evidence(solution)),('oracle_ports',oracle_port_evidence(document))]:
                    stamp=time.perf_counter()
                    changed=realize_ports(solution.graph,solution.occurrences,evidence,solution.prior)
                    seconds=time.perf_counter()-stamp;stamp=time.perf_counter()
                    audit=validate(changed,solution.graph.site_boundaries)
                    result[name]=dict(summarize(changed,audit),solveSeconds=seconds,validationSeconds=time.perf_counter()-stamp,
                        evidenceCount=len(evidence),oracle=name=='oracle_ports')
                result['circulation']=public_circulation(solution,.65)
            append(output/'cases.jsonl',result)
        except Exception as exc:
            errors+=1;result['error']=f'{type(exc).__name__}: {exc}';append(output/'cases.jsonl',result)
        print(json.dumps(dict(case=index+1,total=len(selected),error=result.get('error'),elapsed=time.perf_counter()-start)),flush=True)
    manifest.update(status='complete',cases=len(selected),errors=errors,elapsedSeconds=time.perf_counter()-start)
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--phase',choices=('validation','speed'),default='validation')
    main(p.parse_args())
