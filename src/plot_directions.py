"""Measured parcel directions, optional proposals and intrinsic policy inputs.

Boundary edge axes retain triangles' three directions; area moments add the
long axis of narrow parcels. Neither is an angle restriction or a grid recipe.
"""
import math
import random
from geometry import compute_polygon_second_moments


def descriptors(graph,floor):
    raw=getattr(graph,'site_boundaries',{}).get(floor,[])
    points=tuple((float(p['x']),float(p['y'])) if isinstance(p,dict) else tuple(p) for p in raw)
    cache=getattr(graph,'_plot_direction_cache',None)
    if cache is None:cache=graph._plot_direction_cache={}
    if floor in cache and cache[floor][0]==points:return cache[floor][1]
    axes=[]
    for a,b in zip(points,points[1:]+points[:1]):
        dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
        if length<1e-9:continue
        angle=math.atan2(dy,dx)%math.pi
        match=next((axis for axis in axes if abs(math.sin(angle-axis[0]))<1e-7),None)
        if match is None:axes.append([angle,length])
        else:match[1]+=length
    moments=compute_polygon_second_moments(points) if len(points)>=3 else None
    perimeter=sum(weight for _,weight in axes) or 1.
    result=dict(axes=[dict(angle=angle,weight=weight/perimeter) for angle,weight in sorted(axes,key=lambda p:-p[1])],
        principalAngle=moments['angle_rad'] if moments else 0.,aspectRatio=moments['aspect_ratio'] if moments else 1.)
    cache[floor]=(points,result);return result


def features(graph,floor,origin,position,orientation=0.):
    desc=descriptors(graph,floor);dx,dy=position[0]-origin[0],position[1]-origin[1]
    bearing=math.atan2(dy,dx) if math.hypot(dx,dy)>1e-9 else orientation
    axes=desc['axes'];angle=desc['principalAngle'];anisotropy=1-1/max(1.,desc['aspectRatio'])
    c2=sum(a['weight']*math.cos(2*(bearing-a['angle'])) for a in axes)
    s2=sum(a['weight']*math.sin(2*(bearing-a['angle'])) for a in axes)
    c4=sum(a['weight']*math.cos(4*(bearing-a['angle'])) for a in axes)
    s4=sum(a['weight']*math.sin(4*(bearing-a['angle'])) for a in axes)
    return [c2,s2,c4,s4,anisotropy*math.cos(2*(bearing-angle)),anisotropy*math.sin(2*(bearing-angle)),anisotropy,
            max((abs(math.cos(bearing-a['angle'])) for a in axes),default=0.)]


def candidates(bank,floor,limit=4):
    nodes=list(bank.floor_nodes[floor]);desc=descriptors(bank.graph,floor)
    if not nodes or not desc['axes']:return []
    rng=random.Random(491+len(bank.graph.nodes)*104729+floor);rng.shuffle(nodes)
    axes=[(a['angle'],a['weight']) for a in desc['axes']]
    if desc['aspectRatio']>1.05:axes.append((desc['principalAngle'],1-1/desc['aspectRatio']))
    observed=[bank.vocabulary.lengths[k] for k in bank.vocabulary._length_keys]
    result=[]
    for k in range(limit):
        node=nodes[k%len(nodes)];bearing=rng.choices([a for a,w in axes],[w for a,w in axes])[0]+rng.choice((0.,math.pi))
        # Reuse observed lengths OR explore a continuous length, never a bay grid.
        span=rng.choice(observed) if observed and k%2==0 else rng.uniform(2.5,2*bank.prior.radius)
        result.append(dict(x=node.x+span*math.cos(bearing),y=node.y+span*math.sin(bearing),anchor_node=node.node_id,
            span=span,source='plot_direction',angleSource='measured_plot',lengthSource='observed' if observed and k%2==0 else 'continuous'))
    return result
