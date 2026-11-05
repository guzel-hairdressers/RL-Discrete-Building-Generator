"""Whole-edge glazed/solid facade assignments on realized module footprints.

The finite facade allocator is conservative, not a proof that no other opening layout
exists. Footprint reuse does not imply identical glazing/fabrication variants.
This helper is used only by the realized validator, never by graph training.
"""
import math
import numpy as np


def required_frontage(area, frontage=2., reference_area=15.):
    return frontage*max(1.,area/reference_area)


def cone_distance(a, b, normal, degrees=60., target_normal=None):
    """Minimum glazed-edge-to-edge distance inside A's outward cone.

    Clip the four endpoint differences by the two cone inequalities. This
    measures whole edges, including oblique and endpoint-only conflicts;
    checking window midpoints would miss these. Returns infinity outside cone.
    """
    a0,a1=a;b0,b1=b
    nx,ny=normal;tan=math.tan(math.radians(degrees/2))
    polygon=[(b0[0]-a0[0],b0[1]-a0[1]),(b1[0]-a0[0],b1[1]-a0[1]),
             (b1[0]-a1[0],b1[1]-a1[1]),(b0[0]-a1[0],b0[1]-a1[1])]
    planes=[(nx,ny,1e-9),(tan*nx-ny,tan*ny+nx,0.),(tan*nx+ny,tan*ny-nx,0.)]
    if target_normal is not None:planes.append((-target_normal[0],-target_normal[1],1e-9))
    for px,py,threshold in planes:
        clipped=[]
        for p,q in zip(polygon,polygon[1:]+polygon[:1]):
            u=p[0]*px+p[1]*py-threshold;v=q[0]*px+q[1]*py-threshold
            if u>=0.:clipped.append(p)
            if (u<0.)!=(v<0.):
                fraction=u/(u-v)
                clipped.append((p[0]+(q[0]-p[0])*fraction,p[1]+(q[1]-p[1])*fraction))
        polygon=clipped
        if not polygon:return math.inf
    best=math.inf
    for p,q in zip(polygon,polygon[1:]+polygon[:1]):
        dx,dy=q[0]-p[0],q[1]-p[1];den=dx*dx+dy*dy
        fraction=min(1.,max(0.,-(p[0]*dx+p[1]*dy)/den)) if den>1e-20 else 0.
        best=min(best,math.hypot(p[0]+dx*fraction,p[1]+dy*fraction))
    return best


def conflict(a,b,separation,cone):
    # A window looking at the back of another facade is not visible from it.
    # Occlusion by intervening built space is conservatively NOT discounted:
    # this cannot certify a privacy violation away by putting a blank screen
    # in front of a window. Report this finite solver limitation explicitly.
    return (cone_distance(a['segment'],b['segment'],a['normal'],cone,b['normal'])<separation-1e-7 or
            cone_distance(b['segment'],a['segment'],b['normal'],cone,a['normal'])<separation-1e-7)


def nearby_pairs(candidates,separation):
    if not candidates:return
    centers=np.asarray([np.mean(c['segment'],axis=0) for c in candidates])
    half=np.asarray([c['length']/2 for c in candidates])
    for j in range(len(candidates)):
        delta=centers[j+1:]-centers[j]
        possible=np.flatnonzero(np.sum(delta*delta,axis=1)<(separation+half[j]+half[j+1:])**2)
        for offset in possible:yield j,j+1+int(offset)


def allocate(candidates, required, separation=25., cone=60.):
    """Bounded whole-edge allocation; blank walls are absent from the conflict graph.

    Three deterministic orderings retain the least-deficit opening arrangement.
    Missing frontage is unresolved, not evidence of geometric impossibility.
    """
    n=len(candidates);conflicts=[set() for _ in candidates]
    for j,k in nearby_pairs(candidates,separation):
        a,b=candidates[j],candidates[k]
        if a['occurrenceId']!=b['occurrenceId'] and conflict(a,b,separation,cone):
            conflicts[j].add(k);conflicts[k].add(j)
    by_room={oid:[] for oid in required}
    for j,c in enumerate(candidates):by_room[c['occurrenceId']].append(j)
    available={oid:sum(candidates[j]['length'] for j in indices) for oid,indices in by_room.items()}
    # Geometry breaks ordinary ties without relying on insertion order/node IDs.
    key=lambda oid:(available[oid]/required[oid],tuple(sorted(tuple(np.mean(candidates[j]['segment'],axis=0)) for j in by_room[oid])))
    ordered=sorted(required,key=key);best=None
    for order in (ordered,list(reversed(ordered)),sorted(required,key=lambda oid:(-required[oid],key(oid)))):
        blocked=set();selected=[];frontage={oid:0. for oid in required}
        for oid in order:
            indices=sorted(by_room[oid],key=lambda j:(len(conflicts[j]),-candidates[j]['skyShare'],tuple(candidates[j]['segment'][0])))
            for j in indices:
                if frontage[oid]>=required[oid]-1e-7:break
                if j in blocked:continue
                c=dict(candidates[j]);length=c['length']
                selected.append(c);frontage[oid]+=length;blocked.update(conflicts[j])
        score=(sum(min(1.,frontage[o]/required[o]) for o in required),sum(frontage.values()))
        if best is None or score>best[0]:best=(score,selected,frontage)
    return dict(windows=best[1] if best else [],frontage=best[2] if best else {},
                candidateCount=n,conflictPairs=sum(map(len,conflicts))//2,
                status='whole_edge_glazing_allocation',occlusionTreatment='conservative_no_privacy_discount',
                openingReuse='occurrence_fitout_not_fabrication_reuse')
