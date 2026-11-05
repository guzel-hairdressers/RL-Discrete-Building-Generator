"""Fast opening-budget proxy. No windows are placed or certified here.

An opportunity carries scalar frontage and an estimated facade direction/point
from the shared constraints. Pairwise uncertainty envelopes approximate the
window cone. Geometry realization owns actual intervals and the exact rule.
"""
import numpy as np
import math


def allocate(opportunities,required,separation,cone):
    n=len(opportunities);conflicts=[set() for _ in opportunities]
    if n:
        points=np.asarray([c['estimatedPoint'] for c in opportunities])
        normals=np.asarray([c['normal'] for c in opportunities])
        half=np.asarray([c['length']/2 for c in opportunities])
        for j,a in enumerate(opportunities):
            delta=points[j+1:]-points[j];d=np.linalg.norm(delta,axis=1)
            along=delta@normals[j];back=-np.sum(delta*normals[j+1:],axis=1)
            # Glazed edges are not realized. Inflate the angular footprint and
            # subtract its positional uncertainty from the estimated distance.
            margin=half[j]+half[j+1:]
            angular=np.minimum(math.pi/2,math.radians(cone/2)+np.arctan2(margin,np.maximum(d,1e-9)))
            facing=(along>=d*np.cos(angular))|(back>=d*np.cos(angular))
            possible=(d-margin<separation)&facing&(along>1e-7)&(back>1e-7)
            for offset in np.flatnonzero(possible):
                k=j+1+int(offset)
                if a['occurrenceId']!=opportunities[k]['occurrenceId']:
                    conflicts[j].add(k);conflicts[k].add(j)
    by_room={oid:[] for oid in required}
    for j,c in enumerate(opportunities):by_room[c['occurrenceId']].append(j)
    available={oid:sum(opportunities[j]['length'] for j in rows) for oid,rows in by_room.items()}
    key=lambda oid:(available[oid]/required[oid],tuple(sorted(tuple(opportunities[j]['estimatedPoint']) for j in by_room[oid])))
    order=sorted(required,key=key);best=None
    for rooms in (order,list(reversed(order))):
        blocked=set();budgets=[];frontage={oid:0. for oid in required}
        for oid in rooms:
            for j in sorted(by_room[oid],key=lambda j:(len(conflicts[j]),-opportunities[j]['skyShare'],tuple(opportunities[j]['estimatedPoint']))):
                if frontage[oid]>=required[oid]-1e-7:break
                if j in blocked:continue
                c=opportunities[j];amount=c['length']
                budgets.append(dict(c,estimatedFrontage=amount));frontage[oid]+=amount;blocked.update(conflicts[j])
        score=sum(min(1.,frontage[oid]/required[oid]) for oid in required)
        if best is None or score>best[0]:best=score,budgets,frontage
    return dict(windows=[],openingBudgets=best[1] if best else [],frontage=best[2] if best else {},
        status='graph_frontage_privacy_proxy',candidateCount=n,conflictPairs=sum(map(len,conflicts))//2,
        uncertainty='opening locations and cone visibility require realized validation',
        openingReuse='shape_reuse_only_opening_fitout_unresolved')
