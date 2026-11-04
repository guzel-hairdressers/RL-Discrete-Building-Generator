"""Shared convex modules as numeric half-space constraints, without room polygons.

Growth pools complementary evidence into at most max_types prototypes. Required
contacts are checked as overlapping scalar intervals in both modules' frames.
Only explicit inference/preview converts these constraints to polygon vertices.
"""
from collections import Counter,defaultdict
from dataclasses import dataclass,field
from functools import lru_cache
import math
from bisect import bisect_left,bisect_right
import numpy as np
from graph_proxy import SpatialNodes,root_id,origin_fits


def rotate(v,a):
    c,s=math.cos(a),math.sin(a)
    return c*v[0]-s*v[1],s*v[0]+c*v[1]


@lru_cache(maxsize=32768)
def plane_key(p):return tuple(round(float(v),8) for v in p)


@lru_cache(maxsize=32768)
def displacement_plane(v,angle):
    d=math.hypot(*v)
    if d<1e-8:return None
    x,y=rotate((v[0]/d,v[1]/d),-angle)
    return plane_key((x,y,d/2))


@dataclass(frozen=True)
class Shape:
    planes: tuple
    required: frozenset
    intervals: dict
    area: float
    prior_boundary: bool
    centers: object = field(compare=False,repr=False)
    tangents: object = field(compare=False,repr=False)
    limits: object = field(compare=False,repr=False)
    faces: tuple = field(compare=False,repr=False)
    face_angles: tuple = field(compare=False,repr=False)
    prior_planes: frozenset = field(compare=False,repr=False)
    support_cache: dict = field(default_factory=dict,compare=False,repr=False)

    def interval(self,key):
        cached=self.intervals.get(key)
        if cached is not None:return cached
        # Indexed numeric contact aliases, tighter than the oracle's existing
        # micrometre tolerance. No array scan for every rejected proposal.
        length=math.hypot(*key[:2]);nx,ny=key[0]/length,key[1]/length
        bound=key[2]/length;angle=math.atan2(ny,nx)%(2*math.pi)
        queries=[angle]
        if angle<1e-7:queries.append(angle+2*math.pi)
        if angle>2*math.pi-1e-7:queries.append(angle-2*math.pi)
        lower=math.inf;upper=-math.inf
        for query in queries:
            for i in range(bisect_left(self.face_angles,query-1e-7),bisect_right(self.face_angles,query+1e-7)):
                _,_,_,distance,cx,cy,tx,ty,lo,hi=self.faces[i]
                if abs(distance-bound)>1e-7:continue
                center=-cx*ny+cy*nx;slope=-tx*ny+ty*nx
                a,b=center+slope*lo,center+slope*hi
                lower=min(lower,a,b);upper=max(upper,a,b)
        if lower==math.inf:return None
        result=(lower,upper);self.intervals[key]=result
        return result

    def support(self,normal):
        key=tuple(normal)
        if key not in self.support_cache:
            n=np.asarray(normal)
            slope=self.tangents@n
            if len(self.support_cache)>=512:
                self.support_cache.pop(next(iter(self.support_cache)))
            self.support_cache[key]=float(np.max(self.centers@n+np.maximum(
                slope*self.limits[:,0],slope*self.limits[:,1])))
        return self.support_cache[key]


@lru_cache(maxsize=16)
def prior_constraints(prior):
    return frozenset((math.cos(2*math.pi*(i+.5)/prior.directions),
        math.sin(2*math.pi*(i+.5)/prior.directions),prior.radius*math.cos(math.pi/prior.directions))
        for i in range(prior.directions))


@lru_cache(maxsize=32768)
def normalized_plane_key(row):
    length=math.hypot(*row[:2])
    return (round(row[0]/length,12),round(row[1]/length,12)),row[2]/length


@lru_cache(maxsize=4096)
def make_shape(planes,required,prior,retained_prior=None):
    # The adapter's explicit regular prior is represented by inequalities, not
    # vertices. Every other observation is a unit-normal midpoint inequality.
    prior_planes=prior_constraints(prior) if retained_prior is None else retained_prior
    obs={plane_key(p) for p in set(planes)|set(required) if p[2]<prior.radius+1e-8}
    # Parallel half-spaces contribute one facet, at their strongest bound.
    # Counting almost identical offsets as separate facets inflated areas and
    # could split contact intervals inconsistently with the polygon adapter.
    parallel={}
    for row in sorted(prior_planes|obs):
        key,distance=normalized_plane_key(row)
        if key not in parallel or distance<parallel[key][0]:parallel[key]=(distance,row)
    rows=sorted(value[1] for value in parallel.values())
    if any(p[2]<=0 for p in rows):return None
    data=np.asarray(rows,dtype=float)
    # Rounded keys are identifiers, not unit-vector guarantees. Normalize the
    # actual equations before support-line projection, especially for nearly
    # parallel observations; otherwise pruning can enlarge the shared module.
    lengths=np.linalg.norm(data[:,:2],axis=1)
    normals=data[:,:2]/lengths[:,None];bounds=data[:,2]/lengths
    # Projection intervals on each support line. O(C²) on small prototype
    # arrays, independent of how many rooms share the prototype.
    tangents=np.column_stack((-normals[:,1],normals[:,0]))
    coefficients=normals@tangents.T
    residual=bounds[:,None]-normals@(normals*bounds[:,None]).T
    ratios=np.divide(residual,coefficients,out=np.zeros_like(residual),where=np.abs(coefficients)>1e-10)
    # The prior half-spaces already bound every support line. An additional
    # circle clamp would introduce a different realizer and lose corner area.
    lower=np.max(np.where(coefficients < -1e-10,ratios,-np.inf),axis=0)
    upper=np.min(np.where(coefficients > 1e-10,ratios,np.inf),axis=0)
    infeasible=np.any((np.abs(coefficients)<=1e-10)&(residual < -1e-12),axis=0)
    spans=np.where(infeasible,0.,np.maximum(0.,upper-lower))
    intervals={row:(float(lo),float(hi)) for row,lo,hi,length in zip(rows,lower,upper,spans) if length>1e-7}
    # Divergence theorem: area = 1/2 Σ support_distance * facet_length.
    # Exact for this bounded convex half-space model; no vertices are produced.
    area=float(.5*np.dot(bounds,spans))
    if not prior.min_area-1e-7<=area<=prior.max_area+1e-7:return None
    active=spans>1e-7
    centers=normals[active]*bounds[active,None]
    ts=tangents[active];limits=np.column_stack((lower[active],upper[active]))
    for array in (centers,ts,limits):array.flags.writeable=False
    faces=tuple(sorted((float(math.atan2(ny,nx)%(2*math.pi)),float(nx),float(ny),float(bound),
        float(c[0]),float(c[1]),float(t[0]),float(t[1]),float(lim[0]),float(lim[1]))
        for (nx,ny),bound,c,t,lim in zip(normals[active],bounds[active],centers,ts,limits)))
    shape=Shape(tuple(p for p in sorted(obs) if p in intervals),frozenset(required),intervals,area,
                 any(p in intervals for p in prior_planes),centers,ts,limits,faces,tuple(f[0] for f in faces),frozenset(p for p in prior_planes if p in intervals))
    if any(shape.interval(key) is None or shape.interval(key)[1]-shape.interval(key)[0]<prior.min_contact-1e-6 for key in required):return None
    return shape


def shape_with(base,extra,required,prior):
    extras=set(extra)
    added=frozenset(required)
    req=(base.required if not added else base.required|added) if base else added
    if base is not None:
        # Repeated modules usually receive redundant neighborhood evidence.
        # Cached scalar support proves that without solving the prototype again.
        extras={p for p in extras if p not in base.planes and base.support(p[:2])>p[2]+1e-9}
        if not extras:
            if req==base.required:return base
            if any(base.interval(key) is None or base.interval(key)[1]-base.interval(key)[0]<prior.min_contact-1e-6 for key in added-base.required):return None
            return Shape(base.planes,req,base.intervals,base.area,base.prior_boundary,
                         base.centers,base.tangents,base.limits,base.faces,base.face_angles,base.prior_planes,base.support_cache)
    planes=tuple(sorted(set(base.planes if base else ())|extras))
    # Adding cuts cannot reactivate a previously redundant prior inequality.
    # Retain active prior faces instead of rebuilding all 64 rows per trial.
    return make_shape(planes,req,prior,base.prior_planes if base else None)


@dataclass
class Instance:
    id: str
    nodes: list
    prototype: str
    angle: float

    @property
    def origin(self):return self.nodes[0].x,self.nodes[0].y


@dataclass
class PlacementPlan:
    x: float
    y: float
    floor: int
    scope: str
    prototype: str
    angle: float
    shapes: dict
    contacts: list
    filled: float
    type_count: int
    singleton_count: int


class GraphDictionary:
    def __init__(self,graph,max_types=15):
        self.graph=graph;self.prior=graph.size_prior;self.max_types=max_types
        from relative_vocabulary import RelativeVocabulary
        self.vocabulary=RelativeVocabulary()
        self.instances={};self.shapes={};self.members=defaultdict(set);self.copy_counts=Counter()
        self.floor_nodes=defaultdict(list);self.incident=defaultdict(list);self.links=defaultdict(set)
        self.spatial=SpatialNodes(graph,self.prior.radius)
        groups=defaultdict(list)
        for n in graph.nodes.values():groups[root_id(n)].append(n);self.floor_nodes[n.floor_index].append(n)
        if len(groups)!=1:raise ValueError('new shared dictionary needs one initial occurrence')
        for oid,nodes in groups.items():
            pid='module_1';self.shapes[pid]=make_shape((),frozenset(),self.prior)
            if self.shapes[pid] is None:raise ValueError('size prior cannot define initial module')
            self.instances[oid]=Instance(oid,nodes,pid,0.);self.members[pid].add(oid);self.copy_counts[pid]+=len(nodes)
            for n in nodes:n.module_id=pid;n.orientation=0.;n.area=self.shapes[pid].area
        self.initial_fits={f:all(origin_fits((n.x,n.y),graph.site_boundaries[f],
            getattr(graph,'site_holes',{}).get(f,()),self.prior.radius) for n in nodes)
            for f,nodes in self.floor_nodes.items()} if hasattr(graph,'site_boundaries') else {f:True for f in self.floor_nodes}
        self.rejections=Counter();self._distance_index=None

    def _interval(self,shape,origin,angle,other):
        key=displacement_plane((other[0]-origin[0],other[1]-origin[1]),angle)
        return shape.interval(key)

    def contact(self,a,pa,aa,b,pb,ab):
        ia=self._interval(pa,a,aa,b);ib=self._interval(pb,b,ab,a)
        if ia is None or ib is None:return 0.
        return max(0.,min(ia[1],-ib[0])-max(ia[0],-ib[1]))

    def _preserves_edges(self,changed,check_all=False):
        seen=set()
        for pid,shape in changed.items():
            if pid not in self.shapes or (not check_all and shape.planes==self.shapes[pid].planes):continue
            for edge in self.incident[pid]:
                key=(edge.u,edge.v)
                if key in seen:continue
                seen.add(key)
                a=self.instances[root_id(self.graph.nodes[edge.u])]
                b=self.instances[root_id(self.graph.nodes[edge.v])]
                if self.contact(a.origin,changed.get(a.prototype,self.shapes[a.prototype]),a.angle,
                                b.origin,changed.get(b.prototype,self.shapes[b.prototype]),b.angle)<self.prior.min_contact-1e-6:return False
        return True

    def _area_total(self,changed):
        return sum(changed.get(pid,self.shapes[pid]).area*count for pid,count in self.copy_counts.items())

    def frontier_candidates(self,floor,limit=24):
        import random
        rng=random.Random(173+len(self.graph.nodes)*104729+floor)
        anchors=list(self.floor_nodes[floor]);rng.shuffle(anchors)
        result=[];seen=set()
        for node in anchors:
            instance=self.instances[root_id(node)]
            links=sorted(self.links[instance.prototype]);rng.shuffle(links)
            for dx,dy,pid,relative_angle in links:
                vx,vy=rotate((dx,dy),instance.angle);x,y=node.x+vx,node.y+vy
                key=(round(x,6),round(y,6),pid)
                if key in seen:continue
                seen.add(key)
                if any((n.x-x)**2+(n.y-y)**2<2.5**2 for n in self.spatial.near(floor,x,y)):continue
                result.append(dict(x=x,y=y,anchor_node=node.node_id,span=math.hypot(dx,dy),
                    source='shared_module_contact',preferredPrototype=pid,
                    preferredAngle=instance.angle+relative_angle))
                if len(result)>=limit:return result
        return result

    def probe(self,x,y,floor,scope,min_distance=2.5,preferred_pid=None,preferred_angle=None):
        if not all(self.initial_fits.values()):return []
        floors=range(self.graph.num_floors) if scope=='multi_floor' else (floor,)
        near={f:self.spatial.near(f,x,y) for f in floors}
        if any((n.x-x)**2+(n.y-y)**2<min_distance**2 for nodes in near.values() for n in nodes):return []
        vectors={(n.x-x,n.y-y) for nodes in near.values() for n in nodes}
        if not vectors:return []
        arms=sorted((math.hypot(dx,dy)/2,math.atan2(dy,dx)) for dx,dy in vectors)
        options=[]
        if preferred_pid is not None:
            if preferred_pid not in self.shapes:return []
            options=[(preferred_pid,preferred_angle)]
        else:
            if self._distance_index is None:
                indexed=sorted((b,pid,math.atan2(ny,nx)) for pid,shape in self.shapes.items() for nx,ny,b in shape.planes)
                self._distance_index=([row[0] for row in indexed],indexed)
            offsets,indexed=self._distance_index
            angles=defaultdict(set)
            for distance,world_angle in arms:
                for b,pid,local_angle in indexed[bisect_left(offsets,distance-1e-6):bisect_right(offsets,distance+1e-6)]:
                    angles[pid].add(round((world_angle-local_angle)%(2*math.pi),10))
            for pid,shape in self.shapes.items():
                if not shape.planes:angles[pid].add(arms[0][1])
                options.extend((pid,angle) for angle in sorted(angles[pid]))
        new_pid=f'module_{len(self.shapes)+1}'
        if preferred_pid is None and len(self.shapes)<self.max_types:options.append((new_pid,arms[0][1]))
        if not options:
            self.rejections['dictionary_incompatible']+=1
            return []
        # Only build constraint deltas after an orientation/type correspondence
        # exists. Continuous proposals usually fail that cheap indexed test.
        extra=defaultdict(set)
        for nodes in near.values():
            for n in nodes:
                instance=self.instances[root_id(n)]
                plane=displacement_plane((x-n.x,y-n.y),instance.angle)
                if plane:extra[instance.prototype].add(plane)
        changed={}
        for pid,planes in extra.items():
            shape=shape_with(self.shapes[pid],planes,(),self.prior)
            if shape is None:self.rejections['existing_required_contact']+=1;return []
            changed[pid]=shape
        best_existing=None;new_option=None
        for pid,angle in options:
            planes={displacement_plane(v,angle) for v in vectors}
            shape=shape_with(changed.get(pid,self.shapes.get(pid)),planes,(),self.prior)
            if shape is None:continue
            trial={**changed,pid:shape}
            contacts=[];requirements=defaultdict(set);attached=set()
            for f,nodes in near.items():
                for n in nodes:
                    instance=self.instances[root_id(n)]
                    length=self.contact((x,y),shape,angle,instance.origin,
                        trial.get(instance.prototype,self.shapes[instance.prototype]),instance.angle)
                    if length>=self.prior.min_contact-1e-6:
                        contacts.append((f,n.node_id,length))
                        requirements[pid].add(displacement_plane((n.x-x,n.y-y),angle))
                        requirements[instance.prototype].add(displacement_plane((x-n.x,y-n.y),instance.angle))
                        if n.cell_type.value!='void':attached.add(f)
            if set(floors)!=attached:continue
            valid=True
            for required_pid,rows in requirements.items():
                revised=shape_with(trial[required_pid],(),rows,self.prior)
                if revised is None:valid=False;break
                trial[required_pid]=revised
            if not valid or not self._preserves_edges(trial):continue
            size=self._area_total(trial)+trial[pid].area*len(floors)
            counts={p:len(members) for p,members in self.members.items()};counts[pid]=counts.get(pid,0)+1
            plan=PlacementPlan(x,y,floor,scope,pid,angle,trial,contacts,size,len(counts),sum(v==1 for v in counts.values()))
            if pid==new_pid:new_option=plan
            elif best_existing is None or size>best_existing.filled:best_existing=plan
        if best_existing is not None and new_option is not None and abs(best_existing.filled-new_option.filled)<1e-6:
            def signature(plan):
                return {tuple(round(v,6) for v in (*rotate((nx,ny),plan.angle),b))
                        for _,nx,ny,b,*_ in plan.shapes[plan.prototype].faces}
            if signature(best_existing)==signature(new_option):new_option=None
        result=[p for p in (best_existing,new_option) if p is not None]
        if not result:self.rejections['dictionary_incompatible']+=1
        return result

    def commit(self,plan,node_id):
        from typed_cell import CellType,VerticalScope
        if any(pid not in self.shapes or shape.planes!=self.shapes[pid].planes for pid,shape in plan.shapes.items()):
            self._distance_index=None
        self.shapes.update(plan.shapes)
        self.graph.add_node(node_id,plan.x,plan.y,floor_index=plan.floor,scope=VerticalScope(plan.scope),cell_type=CellType.ROOM)
        nodes=[self.graph.nodes[node_id]]
        if plan.scope=='multi_floor':nodes.extend(self.graph.nodes[f'{node_id}_f{f:02d}'] for f in range(self.graph.num_floors) if f!=plan.floor)
        instance=Instance(node_id,nodes,plan.prototype,plan.angle)
        self.instances[node_id]=instance;self.members[plan.prototype].add(node_id);self.copy_counts[plan.prototype]+=len(nodes)
        for n in nodes:
            self.spatial.cells[self.spatial.key(n.floor_index,n.x,n.y)].append(n)
            self.floor_nodes[n.floor_index].append(n)
        by_floor={n.floor_index:n for n in nodes}
        for f,nid,length in plan.contacts:
            edge=self.graph.add_edge(by_floor[f].node_id,nid,shared_length=length,
                properties={'relation':'construction','validated':False,'constraint_checked':True})
            self.incident[plan.prototype].append(edge)
            other=self.instances[root_id(self.graph.nodes[nid])].prototype
            if other!=plan.prototype:self.incident[other].append(edge)
            neighbor=self.instances[root_id(self.graph.nodes[nid])]
            dx,dy=neighbor.origin[0]-plan.x,neighbor.origin[1]-plan.y
            vx,vy=rotate((dx,dy),-plan.angle)
            self.links[plan.prototype].add((vx,vy,other,neighbor.angle-plan.angle))
            vx,vy=rotate((-dx,-dy),-neighbor.angle)
            self.links[other].add((vx,vy,plan.prototype,plan.angle-neighbor.angle))

        self.vocabulary.observe(self.graph,[n.node_id for n in nodes]+[nid for _,nid,_ in plan.contacts])
        for pid in plan.shapes:
            for oid in self.members[pid]:
                i=self.instances[oid]
                for n in i.nodes:n.module_id=pid;n.orientation=i.angle;n.area=self.shapes[pid].area

    def inference(self,graph=None):
        if graph is not None:
            self.graph=graph
            self.floor_nodes=defaultdict(list)
            self.copy_counts=Counter()
            for i in self.instances.values():
                i.nodes=[graph.nodes[n.node_id] for n in i.nodes]
                for n in i.nodes:self.floor_nodes[n.floor_index].append(n)
                if i.nodes[0].cell_type.value!='void':self.copy_counts[i.prototype]+=len(i.nodes)
            self.spatial=SpatialNodes(graph,self.prior.radius)
        from shared_modules import Inference,Occurrence,Prototype,_bounded_polygon
        occurrences={};prototypes={};unresolved={}
        if not self._preserves_edges(self.shapes,check_all=True):
            unresolved['shared_contacts']='shared module contact constraints are inconsistent'
        for pid,shape in self.shapes.items():
            constraints=[((x,y),b) for x,y,b in shape.planes]
            required=[((x,y),b) for x,y,b in shape.required]
            polygon=_bounded_polygon(tuple(constraints),tuple(required),self.prior)
            if polygon is None:
                for oid in self.members[pid]:unresolved[oid]='implicit prototype unsupported by polygon adapter'
                continue
            prototypes[pid]=Prototype(pid,polygon,sorted(self.members[pid]),shape.prior_boundary,constraints)
        for oid,i in self.instances.items():
            occurrences[oid]=Occurrence(oid,i.nodes,angle=i.angle,prototype=i.prototype if i.prototype in prototypes else None)
        for n in self.graph.nodes.values():
            if root_id(n) not in self.instances:unresolved[root_id(n)]='occurrence has no dictionary assignment'
        return Inference(occurrences,prototypes,unresolved,self.prior,self.graph)

    def view(self):
        for instance in self.instances.values():
            for n in instance.nodes:
                n.area=self.shapes[instance.prototype].area
                n.orientation=instance.angle;n.module_id=instance.prototype
        return dict(graph=self.graph,prior=self.prior,radius=self.prior.radius,spatial=self.spatial,
            groups={oid:i.nodes for oid,i in self.instances.items()},
            areas={oid:self.shapes[i.prototype].area for oid,i in self.instances.items()},
            prototypes={pid:sorted(members) for pid,members in self.members.items()},
            node_labels={n.node_id:i.prototype for i in self.instances.values() for n in i.nodes},
            built=[oid for oid,i in self.instances.items() if i.nodes[0].cell_type.value!='void'],
            counts=Counter(i.prototype for i in self.instances.values() if i.nodes[0].cell_type.value!='void'),
            constraints_valid=dict(self.initial_fits))
