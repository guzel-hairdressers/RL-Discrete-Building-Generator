"""Graph-only growth estimates. No polygon construction, clipping or GEOS.

Live generation reads the shared implicit dictionary. The legacy standalone
star sketch remains provisional. Physical validity is independently audited
on explicit preview or inference completion.
"""
from collections import Counter, defaultdict
from functools import lru_cache
import math


def root_id(n): return n.metadata.get('root_id',n.node_id)


def site_net_area(site):
    """Exact available polygon area; never substitute raster cell counts."""
    if site.get('exactArea') is not None:return float(site['exactArea'])
    def area(loop):
        pts=[(p['x'],p['y']) if isinstance(p,dict) else p for p in loop]
        return abs(math.fsum(x*v-y*u for (x,y),(u,v) in zip(pts,pts[1:]+pts[:1])))/2
    if not site.get('outer'):raise ValueError('site has no exact area or boundary')
    return area(site['outer'])-math.fsum(area(h) for h in site.get('holes',()))


def origin_fits(point,boundary,holes=(),radius=4.5):
    """Conservative scalar site certificate for every radius-bounded prototype."""
    from graph_sampler import GraphSeedSampler
    from typed_cell import BuildingGraph
    boundary=[(p['x'],p['y']) if isinstance(p,dict) else p for p in boundary]
    if not GraphSeedSampler._point_inside_polygon(point,boundary,setback=radius):return False
    for hole in holes:
        hole=[(p['x'],p['y']) if isinstance(p,dict) else p for p in hole]
        if GraphSeedSampler._point_inside_polygon(point,hole):return False
        if BuildingGraph._min_distance_to_boundary(point,hole)<radius:return False
    return True


class SpatialNodes:
    def __init__(self,graph,radius=4.5):
        self.radius=radius;self.width=2*radius;self.cells=defaultdict(list)
        for n in graph.nodes.values():self.cells[self.key(n.floor_index,n.x,n.y)].append(n)

    def key(self,f,x,y):return (f,math.floor(x/self.width),math.floor(y/self.width))

    def near(self,f,x,y):
        _,gx,gy=self.key(f,x,y)
        return [n for dx in (-1,0,1) for dy in (-1,0,1) for n in self.cells.get((f,gx+dx,gy+dy),())
                if (n.x-x)**2+(n.y-y)**2 <= self.width**2+1e-8]


def contact_length(a,b,others,radius):
    """Scalar bisector interval from embedded graph coordinates, no room vertices."""
    return constraint_contact(a,b,[(x-a[0],y-a[1]) for x,y in others if math.dist((x,y),a)>1e-8],
        [(x-b[0],y-b[1]) for x,y in others if math.dist((x,y),b)>1e-8],radius)


def constraint_contact(a,b,a_vectors,b_vectors,radius):
    """Shared bisector interval under both occurrences' pooled half-space evidence."""
    dx,dy=b[0]-a[0],b[1]-a[1];d=math.hypot(dx,dy)
    if d<1e-8 or d>=2*radius:return 0.
    tx,ty=-dy/d,dx/d;mx,my=(a[0]+b[0])/2,(a[1]+b[1])/2
    upper=math.sqrt(max(0.,radius**2-d*d/4));lower=-upper
    for (bx,by),vectors in ((a,a_vectors),(b,b_vectors)):
        for vx,vy in vectors:
            coefficient=2*(vx*tx+vy*ty)
            bound=vx*vx+vy*vy-2*(vx*(mx-bx)+vy*(my-by))
            if abs(coefficient)<1e-10:
                if bound < -1e-8:return 0.
            elif coefficient>0:upper=min(upper,bound/coefficient)
            else:lower=max(lower,bound/coefficient)
            if upper-lower<=0:return 0.
    return max(0.,upper-lower)


def refresh_local_contacts(graph,new_ids,radius,min_contact=.5):
    sketch=GraphSketch(graph)
    contact_radius=radius*math.cos(math.pi/getattr(sketch.prior,'directions',64))
    spatial=sketch.spatial
    affected=set(new_ids)
    for nid in new_ids:
        n=graph.nodes[nid];affected.update(p.node_id for p in spatial.near(n.floor_index,n.x,n.y))
    # A full-height footprint changes on every floor when any floor adds evidence.
    roots={root_id(graph.nodes[nid]) for nid in affected}
    affected={n.node_id for n in graph.nodes.values() if root_id(n) in roots}
    pairs=set()
    for nid in affected:
        n=graph.nodes[nid]
        for m in spatial.near(n.floor_index,n.x,n.y):
            if m.node_id!=nid:pairs.add(tuple(sorted((nid,m.node_id))))
    keep=[]
    # Recompute affected local contact intents; graph changes can occlude old edges.
    for edge in graph.edges_horiz:
        if edge.u not in affected and edge.v not in affected:keep.append(edge)
    graph.edges_horiz=keep
    graph._adj_horiz={nid:set() for nid in graph.nodes}
    for edge in keep:
        graph._adj_horiz[edge.u].add(edge.v);graph._adj_horiz[edge.v].add(edge.u)
    for u,v in sorted(pairs):
        a,b=graph.nodes[u],graph.nodes[v]
        length=constraint_contact((a.x,a.y),(b.x,b.y),sketch.vectors[root_id(a)],
                                  sketch.vectors[root_id(b)],contact_radius)
        if length>=min_contact:
            graph.add_edge(u,v,shared_length=length,properties={'relation':'construction','validated':False})


def star_signature(vectors):
    """Rotation-only quantized star descriptor. A hypothesis, never proof of reuse."""
    return _star_signature(tuple(sorted(vectors)))


@lru_cache(maxsize=32768)
def _star_signature(vectors):
    if not vectors:return ()
    arms=[(math.hypot(x,y),math.atan2(y,x)) for x,y in vectors]
    return min(tuple(sorted((round(d/.1),round(((a-base)%(2*math.pi))/.017453292519943295)) for d,a in arms))
               for _,base in arms)


def radial_area(vectors,radius,samples=24):
    """Scalar angular quadrature of distance constraints, with no polygon output."""
    return _radial_area(tuple(sorted(vectors)),radius,samples)


@lru_cache(maxsize=32768)
def _radial_area(vectors,radius,samples):
    arms=[(math.hypot(x,y),math.atan2(y,x)) for x,y in vectors]
    frames=[(tuple(sorted((round(d,9),round((angle-base)%(2*math.pi),9))
                          for d,angle in arms)),base) for _,base in arms]
    signature=min((sig for sig,base in frames),default=())
    bases=[base for sig,base in frames if sig==signature] or [0.]
    total=0.
    for base in bases:
        for i in range(samples):
            angle=base+2*math.pi*(i+.5)/samples;ux,uy=math.cos(angle),math.sin(angle)
            r=radius
            for x,y in vectors:
                projection=x*ux+y*uy
                if projection>1e-9:r=min(r,(x*x+y*y)/(2*projection))
            total+=r*r
    return math.pi*total/(samples*len(bases))


class GraphSketch:
    def __init__(self,graph):
        if getattr(graph,'module_bank',None) is not None:
            self.__dict__.update(graph.module_bank.view())
            return
        self.graph=graph;self.prior=getattr(graph,'size_prior',None)
        self.radius=getattr(self.prior,'radius',4.5)
        self.spatial=SpatialNodes(graph,self.radius)
        self.groups=defaultdict(list)
        for n in graph.nodes.values():self.groups[root_id(n)].append(n)
        self.signatures={};self.areas={};self.node_labels={};self.vectors={}
        self.prototypes={}
        for oid,nodes in self.groups.items():
            nearby=[]
            for n in nodes:
                nearby.extend((m.x-n.x,m.y-n.y) for m in self.spatial.near(n.floor_index,n.x,n.y)
                              if root_id(m)!=oid)
            nearby=list(dict.fromkeys(nearby))
            self.vectors[oid]=nearby
            signature=star_signature(nearby)
            label=self.signatures.setdefault(signature,f'estimate_{len(self.signatures)+1}')
            estimate=radial_area(nearby,self.radius)
            self.areas[oid]=estimate
            self.prototypes.setdefault(label,[]).append(oid)
            for n in nodes:
                n.area=estimate
                self.node_labels[n.node_id]=label
        self.constraints_valid={}
        bounds=getattr(graph,'site_boundaries',{})
        cache=getattr(graph,'_origin_fit_cache',{})
        graph._origin_fit_cache=cache
        for floor,boundary in bounds.items():
            floor_nodes=[n for n in graph.nodes.values() if n.floor_index==floor]
            holes=getattr(graph,'site_holes',{}).get(floor,[])
            for n in floor_nodes:
                key=(floor,n.x,n.y,self.radius)
                if key not in cache:cache[key]=origin_fits((n.x,n.y),boundary,holes,self.radius)
            self.constraints_valid[floor]=all(cache[(floor,n.x,n.y,self.radius)] and
                getattr(self.prior,'min_area',1.)<=self.areas[root_id(n)]<=getattr(self.prior,'max_area',80.)
                for n in floor_nodes)
        self.built=[oid for oid,nodes in self.groups.items() if nodes[0].cell_type.value!='void']
        self.counts=Counter(self.node_labels[self.groups[oid][0].node_id] for oid in self.built)

    def addition_feasible(self,x,y,floors,min_distance=2.5):
        near={f:self.spatial.near(f,x,y) for f in floors}
        if any(math.hypot(n.x-x,n.y-y)<min_distance for nodes in near.values() for n in nodes):return False
        candidate=list(dict.fromkeys((n.x-x,n.y-y) for nodes in near.values() for n in nodes))
        changed={root_id(n):list(self.vectors[root_id(n)])+[(x-n.x,y-n.y)]
                 for nodes in near.values() for n in nodes}
        lo=getattr(self.prior,'min_area',1.);hi=getattr(self.prior,'max_area',80.)
        for vectors in [candidate,*changed.values()]:
            inner=min([self.radius]+[math.hypot(x,y)/2 for x,y in vectors])
            # Every half-space contains this disk; no area quadrature is needed
            # to prove the default minimum/maximum size constraints.
            if math.pi*inner*inner>=lo and math.pi*self.radius*self.radius<=hi:continue
            if not lo<=radial_area(vectors,self.radius)<=hi:return False
        return all(any(constraint_contact((x,y),(n.x,n.y),candidate,changed[root_id(n)],self.radius*math.cos(math.pi/getattr(self.prior,'directions',64)))
                       >=getattr(self.prior,'min_contact',.5) for n in nodes) for nodes in near.values())

    def preview(self,floor,x,y,anchor,scope,site_area,budget):
        floors=range(self.graph.num_floors) if scope=='multi_floor' else (floor,)
        vectors=list(dict.fromkeys((n.x-x,n.y-y) for f in floors for n in self.spatial.near(f,x,y)))
        signature=star_signature(vectors)
        label=self.signatures.get(signature)
        k=len(self.counts)+(label not in self.counts)
        area=radial_area(vectors,self.radius)
        # Cheap local estimate; does not claim how other prototypes will change.
        filled=sum(self.areas[oid]*len(nodes) for oid,nodes in self.groups.items()
                   if nodes[0].cell_type.value!='void')
        multiplier=self.graph.num_floors if scope=='multi_floor' else 1
        singleton=sum(v==1 for v in self.counts.values())
        return k,singleton,filled+area*multiplier,area

    def metrics(self,floor,site_area=1000.,budget=10):
        nodes=[n for n in self.graph.nodes.values() if n.floor_index==floor]
        filled=sum(self.areas[root_id(n)] for n in nodes if n.cell_type.value!='void')
        rentable=sum(self.areas[root_id(n)] for n in nodes if n.cell_type.value=='room')
        core=sum(self.areas[root_id(n)] for n in nodes if n.cell_type.value=='core')
        bank=getattr(self.graph,'module_bank',None)
        if bank:budget=min(budget,bank.max_types)
        k=len(self.counts);singletons=sum(c==1 for c in self.counts.values())
        budget_cost=10.*(max(0,k-budget)/max(1,budget))**2
        singleton_cost=5.*singletons/max(1,len(self.built))
        ratio=filled/max(1.,site_area)
        underfill=35.*max(0.,1-ratio/.6)**2
        topology=self.graph.validate_circulation_connectivity(floor)
        reuse=sum(c for c in self.counts.values() if c>1)/max(1,len(self.built))
        # Fabricating one prototype serves its first occurrence; subsequent
        # independently placed occurrences earn reuse. Vertical copies and holes
        # are excluded, and legacy provisional stars earn no such credit.
        repeat_fraction=(len(self.built)-k)/max(1,len(self.built)) if bank else 0.
        reuse_bonus=20.*repeat_fraction
        penalty=0. if topology else 20.
        score=80*min(1.,ratio)+15*rentable/max(1.,filled)+reuse_bonus-budget_cost-singleton_cost-underfill-penalty
        result=dict(instanceIdx=floor,floorIndex=floor,filledArea=filled,siteArea=site_area,
            rentableArea=rentable,coreArea=core,moduleCount=len(nodes),exposedPerimeter=0.,
            fillRatio=ratio,rentableRatio=rentable/max(1.,filled),daylightRatio=0.,envelopeDaylightRatio=0.,
            reuseRatio=reuse if bank else 0.,estimatedReuseRatio=reuse,reuseBonus=reuse_bonus,
            constructibilityScore=0.,envelopeEfficiency=0.,exteriorCorridorRatio=0.,triangleRatio=0.,
            constraintsValid=self.constraints_valid.get(floor,True),
            topologyValid=topology,topologyViolations=[] if topology else ['provisional_same_floor_access'],
            totalPartialLength=0.,deepRoomCount=0,depthPenaltyScore=0.,facadeChasmOccludedLength=0.,
            areaVariancePenalty=0.,rawScore=score+underfill,underfillPenalty=underfill,topologyPenalty=penalty,
            facadeChasmPenalty=0.,vocabSize=k,dictLimitBreach=max(0,k-budget),dictBreachPenalty=budget_cost,
            singletonPenalty=singleton_cost,score=score,estimateStatus='implicit_shared_constraints' if bank else 'graph_proxy_uncalibrated',
            moduleIdentityStatus='constraint_checked' if bank else 'provisional',sunExposure=None,daylightAccessibility=None,
            unavailableMetrics=['daylightRatio','constructibilityScore','envelopeEfficiency']+([] if bank else ['confirmedReuseRatio']),
            uncertainty=({'allModuleIdentitiesProvisional':False,'areaMethod':'support_line_integral','numericalTolerance':1e-6}
                         if bank else {'allModuleIdentitiesProvisional':True,'areaQuadratureSamples':24}),
            reuseAudit=dict(prototypeCount=k,independentOccurrences=len(self.built),
                verticalCopies=sum(len(self.groups[oid])-1 for oid in self.built),
                singletonCount=singletons,independentRepeatFraction=repeat_fraction,confirmedReuseRatio=reuse if bank else None))
        if bank and getattr(self.graph,'_spatial_evaluate',False) and getattr(self.graph,'spatial_settings',{}).get('graphSpatialEnabled',False):
            from graph_spatial import evidence
            result.update(evidence(bank).metrics(floor))
        return result
