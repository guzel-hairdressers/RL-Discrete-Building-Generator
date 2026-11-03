"""Shared convex prototype inference. No GEOS/Voronoi calls in inference.

Origins are persistent seeds, never polygon centroids. Midpoint constraints are
an adapter assumption, not a claim about all architectural realizers.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import math
from collections import Counter
from functools import lru_cache


def turn(p, a):
    c, s = math.cos(a), math.sin(a)
    return (c*p[0]-s*p[1], s*p[0]+c*p[1])


def area(p):
    return abs(sum(x*v-y*u for (x,y),(u,v) in zip(p,p[1:]+p[:1])))/2 if p else 0.


def clip(poly, normal, offset, eps=1e-9):
    """Sutherland-Hodgman clipping of a convex polygon against n.x <= b."""
    out=[]
    for a,b in zip(poly,poly[1:]+poly[:1]):
        da=sum(x*y for x,y in zip(normal,a))-offset
        db=sum(x*y for x,y in zip(normal,b))-offset
        if da <= eps: out.append(a)
        if (da < -eps and db > eps) or (da > eps and db < -eps):
            t=da/(da-db)
            out.append((a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1])))
    return out


def face_length(poly, n, b, tol=1e-6):
    on=[p for p in poly if abs(p[0]*n[0]+p[1]*n[1]-b)<tol]
    return max((math.dist(a,c) for a in on for c in on), default=0.)


@dataclass(frozen=True)
class SizePrior:
    radius: float = 4.5
    min_area: float = 1.0
    max_area: float = 80.0
    min_contact: float = 0.5
    directions: int = 64

    def __post_init__(self):
        if not (self.radius>0 and 0<self.min_area<=self.max_area and self.min_contact>0 and self.directions>=16):
            raise ValueError('invalid size prior')


@dataclass
class Occurrence:
    id: str
    nodes: list
    # Rotation maps canonical prototype coordinates into world coordinates.
    angle: float = 0.
    prototype: str | None = None
    constraints: list = field(default_factory=list)
    required: list = field(default_factory=list)

    @property
    def origin(self): return (self.nodes[0].x,self.nodes[0].y)


@dataclass
class Prototype:
    id: str
    polygon: list
    members: list[str]
    prior_boundary: bool
    constraints: list


@dataclass
class Inference:
    occurrences: dict
    prototypes: dict
    unresolved: dict
    prior: SizePrior
    graph: object

    def polygon(self, occurrence):
        o=self.occurrences[occurrence]
        if not o.prototype: return []
        ox,oy=o.origin
        return [(x+ox,y+oy) for x,y in (turn(p,o.angle) for p in self.prototypes[o.prototype].polygon)]

    def reuse(self):
        built=[o for o in self.occurrences.values() if o.nodes[0].cell_type.value!='void' and o.prototype]
        counts=Counter(o.prototype for o in built)
        return {'prototypeCount':len(counts), 'independentOccurrences':len(built),
                'verticalCopies':sum(len(o.nodes)-1 for o in built),
                'singletonCount':sum(c==1 for c in counts.values()),
                'confirmedReuseRatio':sum(c for c in counts.values() if c>1)/max(1,len(built))}


def _groups(graph):
    groups={}
    for n in graph.nodes.values():
        root=n.metadata.get('root_id',n.node_id)
        groups.setdefault(root,[]).append(n)
    return {k:Occurrence(k, sorted(v,key=lambda n:n.floor_index)) for k,v in groups.items()}


@lru_cache(maxsize=8192)
def _bounded_polygon(constraints,required,prior):
    if any(b<=0 for n,b in constraints): return None
    poly=[(prior.radius*math.cos(2*math.pi*i/prior.directions),
           prior.radius*math.sin(2*math.pi*i/prior.directions)) for i in range(prior.directions)]
    for n,b in constraints:
        if b>=prior.radius: continue
        poly=clip(poly,n,b)
        if len(poly)<3:return None
    if not prior.min_area<=area(poly)<=prior.max_area:return None
    if any(face_length(poly,n,b)<prior.min_contact for n,b in required):return None
    return poly


def infer(graph, prior=None):
    """Pool compatible evidence, including partial stars, across the building.

    A merge is allowed only if every required contact survives the pooled
    constraints. Dictionary budgets never participate in geometric equivalence.
    Full-height occurrences contribute evidence from every floor to one shape.
    """
    prior=prior or getattr(graph,"size_prior",None) or SizePrior()
    occ=_groups(graph)
    node_to_occ={n.node_id:k for k,o in occ.items() for n in o.nodes}
    for o in occ.values():
        for n in o.nodes:
            for other in graph.nodes.values():
                if other.floor_index!=n.floor_index or node_to_occ[other.node_id]==o.id: continue
                dx,dy=other.x-n.x,other.y-n.y
                d=math.hypot(dx,dy)
                if d<1e-8:
                    o.constraints.append(((1.,0.),-1.))
                    continue
                # Beyond twice the explicit radius, a bisector cannot cut the
                # prior-bounded prototype. Required distant contacts still fail.
                if d>2*prior.radius and not graph.has_edge(n.node_id,other.node_id):
                    continue
                constraint=((dx/d,dy/d),d/2)
                if constraint not in o.constraints: o.constraints.append(constraint)
                if graph.has_edge(n.node_id,other.node_id) and constraint not in o.required:
                    o.required.append(constraint)
        directions=[math.atan2(n[1],n[0]) for n,b in o.required or o.constraints]
        # An intrinsic frame, with no global orthogonal preference.
        o.angle=min(directions,key=lambda a:tuple(sorted(round((v-a)%(2*math.pi),8) for v in directions))) if directions else o.nodes[0].orientation

    def evidence(o,a):
        return [(turn(n,-a),b) for n,b in o.constraints],[(turn(n,-a),b) for n,b in o.required]

    def build(constraints,required):
        # Pure memoized local inference. Exact inputs retained; no coordinate snapping.
        return _bounded_polygon(tuple(sorted(set(constraints))),tuple(sorted(set(required))),prior)

    # Degree/signature ordering does not use supplied node labels.
    def signature(o):
        cs,rs=evidence(o,o.angle)
        return (-len(rs),tuple(sorted((round(math.atan2(n[1],n[0]),7),round(b,7)) for n,b in rs)),o.origin)
    classes=[]; unresolved={}
    for o in sorted(occ.values(),key=signature):
        own_c,own_r=evidence(o,o.angle)
        own=build(own_c,own_r)
        if own is None:
            unresolved[o.id]='realizer_unsupported: required contacts or size prior infeasible'
            continue
        selected=None
        for j,c in enumerate(classes):
            # Do not collapse unrelated evidence-free occurrences into one type.
            source=o.required or [(n,b) for n,b in o.constraints if b<prior.radius]
            target=c['required'] or [(n,b) for n,b in c['constraints'] if b<prior.radius]
            if not source or not target: continue
            angles=[]
            for n,b in source:
                for cn,cb in target:
                    if abs(b-cb)<1e-6:
                        angles.append(math.atan2(n[1],n[0])-math.atan2(cn[1],cn[0]))
            for a in sorted({round(a % (2*math.pi),10) for a in angles}):
                cs,rs=evidence(o,a)
                # Require actual shared evidence, not merely a feasible smaller shape.
                if not any(math.dist(n,cn)<1e-6 and abs(b-cb)<1e-6 for n,b in (rs or cs) for cn,cb in target): continue
                p=build(c['constraints']+cs,c['required']+rs)
                if p is not None:
                    selected=(j,a,p,cs,rs); break
            if selected: break
        if selected:
            j,a,p,cs,rs=selected; c=classes[j]
            c['polygon']=p
            def unique(rows):
                seen=set();out=[]
                for n,b in rows:
                    key=(round(n[0],10),round(n[1],10),round(b,10))
                    if key not in seen: seen.add(key);out.append((n,b))
                return out
            c['constraints']=unique(c['constraints']+cs)
            c['required']=unique(c['required']+rs)
            c['members'].append(o.id); o.angle=a
        else:
            classes.append(dict(polygon=own,constraints=own_c,required=own_r,members=[o.id]))
    prototypes={}
    for i,c in enumerate(classes):
        pid=f'prototype_{i+1}'
        has_prior=any(math.hypot(*p)>prior.radius*math.cos(math.pi/prior.directions)-1e-6 for p in c['polygon'])
        prototypes[pid]=Prototype(pid,c['polygon'],c['members'],has_prior,c['constraints'])
        for oid in c['members']:
            occ[oid].prototype=pid
            for n in occ[oid].nodes:
                n.module_id=pid; n.orientation=occ[oid].angle
    return Inference(occ,prototypes,unresolved,prior,graph)


def validate(result, boundaries):
    """Independent GEOS oracle. Never clips, repairs, or resizes instances."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    polygons={}; violations=[]; floors={}
    for oid,o in result.occurrences.items():
        if not o.prototype: continue
        poly=Polygon(result.polygon(oid))
        for n in o.nodes:
            polygons[n.node_id]=poly
            site=Polygon(boundaries[n.floor_index])
            if not poly.is_valid or not site.buffer(1e-7).covers(poly):
                violations.append({'kind':'containment','node':n.node_id})
            floors.setdefault(n.floor_index,[]).append((n,poly))
    metrics={}
    for f,rows in floors.items():
        built=[p for n,p in rows if n.cell_type.value!='void']
        for i,(n,p) in enumerate(rows):
            for m,q in rows[i+1:]:
                if p.intersection(q).area>1e-6:
                    violations.append({'kind':'overlap','nodes':[n.node_id,m.node_id]})
        union=unary_union(built)
        metrics[f]={'filledArea':union.area,'exposedPerimeter':union.length}
    contacts,access=contact_pairs(result)
    contact_set={frozenset(e) for e in contacts}
    for e in result.graph.edges_horiz:
        if frozenset((e.u,e.v)) not in contact_set:
            violations.append({'kind':'missing_contact','nodes':[e.u,e.v]})
    adj={nid:set() for nid in polygons}
    for u,v in access:
        adj[u].add(v); adj[v].add(u)
    for f,rows in floors.items():
        seen={n.node_id for n,p in rows if n.cell_type.value=='core'}
        queue=list(seen)
        for nid in queue:
            for other in adj[nid]-seen:
                seen.add(other); queue.append(other)
        for n,p in rows:
            if n.cell_type.value not in ('core','void') and n.node_id not in seen:
                violations.append({'kind':'access','node':n.node_id})
    return {'valid':not violations and not result.unresolved,'violations':violations,
            'unresolved':result.unresolved,'perFloor':metrics,'polygons':polygons}


def contact_pairs(result):
    """Independent realized contact and access edges; holes never carry access."""
    from shapely.geometry import Polygon
    rows=[(n,Polygon(result.polygon(oid))) for oid,o in result.occurrences.items() if o.prototype for n in o.nodes]
    contacts=[]; access=[]
    for i,(n,p) in enumerate(rows):
        for m,q in rows[i+1:]:
            if n.floor_index!=m.floor_index: continue
            # Micrometre tolerance accommodates rigid-transform floating point noise.
            # A point contact contributes only O(tolerance), far below min_contact.
            if p.boundary.buffer(1e-6).intersection(q.boundary).length>=result.prior.min_contact-1e-7:
                contacts.append((n.node_id,m.node_id))
                if n.cell_type.value!='void' and m.cell_type.value!='void': access.append((n.node_id,m.node_id))
    return contacts,access


def missing_required_contacts(result):
    """Algebraic interval check for candidate search; no polygon Boolean calls."""
    node_to_occ={n.node_id:o.id for o in result.occurrences.values() for n in o.nodes}
    missing=[]
    for edge in result.graph.edges_horiz:
        a,b=result.graph.nodes[edge.u],result.graph.nodes[edge.v]
        d=math.hypot(b.x-a.x,b.y-a.y)
        if d<1e-8: missing.append((edge.u,edge.v));continue
        normal=((b.x-a.x)/d,(b.y-a.y)/d)
        tangent=(-normal[1],normal[0]); midpoint=((a.x+b.x)/2,(a.y+b.y)/2)
        intervals=[]
        for nid in (edge.u,edge.v):
            poly=result.polygon(node_to_occ[nid])
            on=[p[0]*tangent[0]+p[1]*tangent[1] for p in poly
                if abs((p[0]-midpoint[0])*normal[0]+(p[1]-midpoint[1])*normal[1])<1e-6]
            intervals.append((min(on),max(on)) if on else (0.,0.))
        if min(p[1] for p in intervals)-max(p[0] for p in intervals)<result.prior.min_contact-1e-6:
            missing.append((edge.u,edge.v))
    return missing
