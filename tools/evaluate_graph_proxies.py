"""Evaluate explicit held-out graph fixtures, retaining invalid cases and raw errors.

Input JSON: {"split":"held_out", "cases":[{"id":..., "floors":N,
"nodes":[{"id":...,"x":...,"y":...,"floor":0,"function":"room"}],
"edges":[["a","b"]],"boundaries":{"0":[[x,y],...]}}]}.
This is calibration tooling, not a throughput benchmark.
"""
import argparse
import json
import sys
import subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from typed_cell import BuildingGraph, CellType
from shared_modules import infer, validate


def evaluate(data):
    if data.get('split')!='held_out': raise ValueError('explicit held_out manifest required')
    rows=[]
    for c in data['cases']:
        try:
            g=BuildingGraph(c['floors'])
            for n in c['nodes']:
                g.add_node(n['id'],n['x'],n['y'],floor_index=n.get('floor',0),cell_type=CellType(n.get('function','room')))
            for u,v in c['edges']:g.add_edge(u,v)
            bounds={int(f):p for f,p in c['boundaries'].items()}
            result=infer(g); actual=validate(result,bounds)
            for f,pts in bounds.items():
                from shapely.geometry import Polygon
                estimate=g.evaluate_graph_metrics(f,site_area=Polygon(pts).area)
                observed=actual['perFloor'].get(f,{}).get('filledArea',0.)
                rows.append(dict(case=c['id'],floor=f,predictedArea=estimate['filledArea'],actualArea=observed,
                    absoluteError=abs(estimate['filledArea']-observed),valid=actual['valid'],
                    uncertainty=estimate['uncertainty'],violations=actual['violations'],unresolved=result.unresolved))
        except Exception as e:
            rows.append(dict(case=c['id'],failure=f'{type(e).__name__}: {e}'))
    errors=[r['absoluteError'] for r in rows if 'absoluteError' in r]
    # Pairwise order agreement avoids claiming correlation on tied/constant data.
    pairs=[(a,b) for i,a in enumerate(rows) for b in rows[i+1:]
           if 'actualArea' in a and 'actualArea' in b and a['actualArea']!=b['actualArea']]
    concordant=sum((a['actualArea']-b['actualArea'])*(a['predictedArea']-b['predictedArea'])>0 for a,b in pairs)
    return dict(rows=rows,areaMAE=sum(errors)/len(errors) if errors else None,
        pairwiseRankingAgreement=concordant/len(pairs) if pairs else None,
        failedCases=sum('failure' in r for r in rows),
        unavailableMetrics=['sun_exposure_calibration','daylight_calibration'],
        revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),manifest=data)

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('manifest');parser.add_argument('--output',required=True)
    args=parser.parse_args()
    Path(args.output).write_text(json.dumps(evaluate(json.loads(Path(args.manifest).read_text())),indent=2))
