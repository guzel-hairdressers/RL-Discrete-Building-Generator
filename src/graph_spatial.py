"""Scalar exposure/clearance evidence from the live shared dictionary.

No polygon realization, clipping, Boolean operations or window/daylight simulation.
Only ROOM occurrences have a daylight obligation. Every occupied function can
obstruct them. Proximity never becomes a contact/access or prototype constraint.
"""
from collections import defaultdict
import heapq
import math
import numpy as np

DEFAULTS = dict(graphSpatialEnabled=True, graphFacadeClearance=4., graphExposureHorizon=30.,
    graphDaylightDepth=6., graphMinRoomExposure=.35, graphMaxAccessDistance=30.,
    graphExposureSampleSpacing=1., graphMinResidentialShare=.65,
    graphMinCoreArea=12., graphMinCoreWidth=2., graphCoreCapacity=500.,graphMinSkyShare=.25,graphMinFill=.4,
    graphWindowFrontage=2.,graphWindowReferenceArea=15.,graphWindowSeparation=25.,graphWindowCone=60.,
    graphMaxCreviceFraction=.05,graphPlotDirections=True)


def settings(graph):
    return dict(DEFAULTS, **{k:v for k,v in getattr(graph,'spatial_settings',{}).items() if k in DEFAULTS})


def shape_token(shape):
    # A retained unique object avoids id reuse after an old prototype is freed.
    return shape.continuity_cache.setdefault('spatial_identity',object())


def rotate(x,y,a):
    c,s=math.cos(a),math.sin(a)
    return c*x-s*y,s*x+c*y


def access_distances(graph,floor,extra_core=None):
    """Origin-length shortest paths; not an interior/egress-distance certificate."""
    nodes={n.node_id:n for n in graph.nodes.values() if n.floor_index==floor and n.cell_type.value!='void'}
    distances={nid:0. for nid,n in nodes.items() if n.cell_type.value=='core' or nid==extra_core}
    queue=[(d,nid) for nid,d in distances.items()];heapq.heapify(queue)
    adjacency=defaultdict(list)
    for e in graph.edges_horiz:
        if e.u in nodes and e.v in nodes:
            d=math.hypot(nodes[e.u].x-nodes[e.v].x,nodes[e.u].y-nodes[e.v].y)
            adjacency[e.u].append((e.v,d));adjacency[e.v].append((e.u,d))
    while queue:
        d,nid=heapq.heappop(queue)
        if d!=distances[nid]:continue
        for other,length in adjacency[nid]:
            new=d+length
            if new<distances.get(other,math.inf):distances[other]=new;heapq.heappush(queue,(new,other))
    return distances


def _samples(shape,spacing):
    """Equal-arc samples on merged collinear implicit supports, all lengths kept.

    Cache by immutable shape + physical spacing. Facet subdivision is normalized
    before sampling; small facets are never discarded based on architectural size.
    """
    key=('exposure_samples',spacing)
    if key not in shape.continuity_cache:
        # make_shape already unifies parallel support constraints. Combine any
        # numerical aliases, rather than letting fragmentation change the score.
        groups=[]
        for _,nx,ny,b,cx,cy,tx,ty,lo,hi in shape.faces:
            group=next((g for g in groups if math.hypot(nx-g[0],ny-g[1])<=1e-7 and abs(b-g[2])<=1e-7),None)
            if group is None:
                group=[nx,ny,b,[]];groups.append(group)
            gx,gy,gb,intervals=group
            # Project each fragment into the same tangent frame before union.
            values=[-gy*(cx+tx*t)+gx*(cy+ty*t) for t in (lo,hi)]
            intervals.append((min(values),max(values)))
        rows=[]
        for nx,ny,b,intervals in groups:
            merged=[]
            for lo,hi in sorted(intervals):
                if merged and lo<=merged[-1][1]+1e-6:merged[-1][1]=max(merged[-1][1],hi)
                else:merged.append([lo,hi])
            for lo,hi in merged:
                count=max(1,math.ceil((hi-lo)/spacing-1e-8));weight=(hi-lo)/count
                for j in range(count):
                    t=lo+(j+.5)*weight
                    rows.append((nx*b-ny*t,ny*b+nx*t,nx,ny,weight))
        shape.continuity_cache[key]=np.asarray(rows,dtype=float).reshape(-1,5)
    return shape.continuity_cache[key]


def _ray_intervals(origins,directions,planes):
    """Slab intersections with a convex half-space object; vectorized per object."""
    normals=planes[:,:2];bounds=planes[:,2]
    slopes=directions@normals.T
    residual=bounds[None,:]-origins@normals.T
    parallel=np.abs(slopes)<1e-10
    ratios=np.divide(residual,slopes,out=np.zeros_like(residual),where=~parallel)
    lo=np.max(np.where(slopes < -1e-10,ratios,-np.inf),axis=1)
    hi=np.min(np.where(slopes > 1e-10,ratios,np.inf),axis=1)
    hit=(hi>=np.maximum(lo,0.)-1e-7)&~np.any(parallel&(residual < -1e-6),axis=1)
    inside=np.all(residual>=-1e-6,axis=1)
    return np.where(inside,0.,np.where(hit,np.maximum(lo,0.),np.inf)),np.where(inside,np.maximum(0.,hi),hi)


class SpatialEvidence:
    def __init__(self,bank):
        self.bank=bank;self.graph=bank.graph;self.options=settings(self.graph)
        self.cache={};self.relations={};self.counters=defaultdict(int)
        self.plane_cache={}
        self.intersection_cache={}
        self.build_candidates=False
        self._index_key=None

    def surface(self,instance):
        shape=self.bank.shapes[instance.prototype]
        samples=_samples(shape,self.options['graphExposureSampleSpacing'])
        c,s=math.cos(instance.angle),math.sin(instance.angle);rotation=np.array([[c,-s],[s,c]])
        return (samples[:,:2]@rotation.T+np.asarray(instance.origin),
                samples[:,2:4]@rotation.T,samples[:,4],shape.area)

    def intersect(self,instance,origins,directions):
        shape=self.bank.shapes[instance.prototype]
        if 'ray_planes' not in shape.continuity_cache:
            shape.continuity_cache['ray_planes']=np.asarray([(nx,ny,b) for _,nx,ny,b,*_ in shape.faces])
        c,s=math.cos(instance.angle),math.sin(instance.angle);rotation=np.array([[c,-s],[s,c]])
        return _ray_intervals((origins-np.asarray(instance.origin))@rotation,
                              directions@rotation,shape.continuity_cache['ray_planes'])

    def intersect_many(self,instances,origins,directions):
        """One grouped NumPy slab reduction, avoiding thousands of tiny calls."""
        if not instances:return np.empty((0,len(origins))),np.empty((0,len(origins)))
        anchor=np.asarray(next(iter(self.bank.instances.values())).origin)
        tables=[];starts=[];offset=0
        for instance in instances:
            shape=self.bank.shapes[instance.prototype]
            key=(instance.id,shape_token(shape),instance.origin,instance.angle,tuple(anchor))
            if key not in self.plane_cache:
                raw=np.asarray([(nx,ny,b) for _,nx,ny,b,*_ in shape.faces])
                c,s=math.cos(instance.angle),math.sin(instance.angle);rotation=np.array([[c,-s],[s,c]])
                normals=raw[:,:2]@rotation.T
                self.plane_cache[key]=np.column_stack((normals,raw[:,2]+normals@(np.asarray(instance.origin)-anchor)))
            table=self.plane_cache[key];tables.append(table);starts.append(offset);offset+=len(table)
        table=np.concatenate(tables);slopes=directions@table[:,:2].T
        residual=table[None,:,2]-(origins-anchor)@table[:,:2].T
        parallel=np.abs(slopes)<1e-10
        ratios=np.divide(residual,slopes,out=np.zeros_like(residual),where=~parallel)
        lo=np.maximum.reduceat(np.where(slopes < -1e-10,ratios,-np.inf),starts,axis=1)
        hi=np.minimum.reduceat(np.where(slopes > 1e-10,ratios,np.inf),starts,axis=1)
        invalid=np.logical_or.reduceat(parallel&(residual < -1e-6),starts,axis=1)
        hit=(hi>=np.maximum(lo,0.)-1e-7)&~invalid
        inside=np.logical_and.reduceat(residual>=-1e-6,starts,axis=1)
        return np.where(inside,0.,np.where(hit,np.maximum(lo,0.),np.inf)).T,np.where(inside,np.maximum(0.,hi),hi).T

    def _index(self):
        # Rebuild cheap origin buckets after a commit, never a whole floor plan.
        key=(len(self.graph.nodes),getattr(self.graph,'pose_revision',0))
        if self._index_key==key:return
        self._index_key=key;self.cells=defaultdict(set)
        self.width=self.options['graphExposureHorizon']+2*self.bank.prior.radius
        for oid,i in self.bank.instances.items():
            for floor in range(max(n.floor_index for n in i.nodes)+1):
                self.cells[(floor,math.floor(i.origin[0]/self.width),math.floor(i.origin[1]/self.width))].add(oid)

    def neighbors(self,origin,floor):
        self._index();x,y=origin;gx,gy=math.floor(x/self.width),math.floor(y/self.width)
        found=set()
        for dx in (-1,0,1):
            for dy in (-1,0,1):found.update(self.cells.get((floor,gx+dx,gy+dy),()))
        # Horizon starts at the facade, not the origin.
        radius=self.options['graphExposureHorizon']+2*self.bank.prior.radius
        return sorted(oid for oid in found if math.dist(origin,self.bank.instances[oid].origin)<=radius)

    def measure(self,oid,floor):
        i=self.bank.instances[oid];o=self.options
        if i.nodes[0].cell_type.value=='void':return None
        # Full-height occurrences share their footprint on every floor. Query
        # the union once; lower objects contribute zero sky angle upstairs.
        # Independent occurrences retain their ordinary floor-local query.
        near=self.neighbors(i.origin,0 if len(i.nodes)>1 else floor)
        # Local footprint changes include remote occurrences of a shared type.
        # A core/room change does not change obstruction but does change obligation.
        signature=tuple((other,shape_token(self.bank.shapes[self.bank.instances[other].prototype]),
                         self.bank.instances[other].origin,self.bank.instances[other].angle,
                         tuple(n.floor_index for n in self.bank.instances[other].nodes),
                         self.bank.instances[other].nodes[0].cell_type.value) for other in near)
        key=(oid,floor)
        if key in self.cache and self.cache[key][0]==signature:
            self.counters['cacheHits']+=1;return self.cache[key][1]
        self.counters['roomsEvaluated']+=1
        shape=self.bank.shapes[i.prototype]
        origins,directions,weights,area=self.surface(i)
        clearance=np.full(len(origins),o['graphExposureHorizon'])
        bands=[]
        contact=np.zeros(len(origins),dtype=bool);nearest=np.full(len(origins),'',dtype=object)
        floor_z=floor*self.graph.floor_height+1.5
        obstacles=[self.bank.instances[other] for other in near if other!=oid and self.bank.instances[other].nodes[0].cell_type.value!='void']
        ray_key=(shape_token(shape),i.origin,i.angle,signature)
        cached=self.intersection_cache.get(oid)
        if cached is None or cached[0]!=ray_key:
            entries,exits=self.intersect_many(obstacles,origins,directions)
            self.intersection_cache[oid]=(ray_key,entries,exits)
        else:_,entries,exits=cached
        for j,distance,exit_distance in zip(obstacles,entries,exits):
            other=j.id
            on_floor=any(n.floor_index==floor for n in j.nodes)
            if on_floor:
                contact|=distance<=1e-5
                update=distance<clearance;clearance[update]=distance[update];nearest[update]=other
            top=(max(n.floor_index for n in j.nodes)+1)*self.graph.floor_height
            bottom=min(n.floor_index for n in j.nodes)*self.graph.floor_height
            # Visibility to the horizon is an explicit finite-range assumption.
            angle=np.arctan2(max(0.,top-floor_z),np.maximum(distance,1e-7))
            low=np.arctan2(max(0.,bottom-floor_z),np.maximum(exit_distance,1e-7))
            obstructed=np.isfinite(distance)&(distance<=o['graphExposureHorizon'])
            bands.append((np.where(obstructed,low,0.),np.where(obstructed,angle,0.)))
        hidden=np.zeros(len(origins))
        if bands:
            lower=np.asarray([a for a,b in bands]);upper=np.asarray([b for a,b in bands])
            order=np.argsort(lower,axis=0);lower=np.take_along_axis(lower,order,axis=0);upper=np.take_along_axis(upper,order,axis=0)
            end=np.zeros(len(origins))
            for lo,hi in zip(lower,upper):
                hidden+=np.maximum(0.,hi-np.maximum(lo,end));end=np.maximum(end,hi)
        sky=np.maximum(0.,1.-hidden/(math.pi/2))
        exposed=~contact
        qualified=exposed&(sky>=o['graphMinSkyShare'])
        # Capacity of usable potential window facade; not illuminance, actual
        # window area or transmitted light through adjacent rooms.
        exposed_length=float(weights@exposed)
        qualified_length=float(weights@qualified)
        weighted_length=float(weights@(qualified*sky))
        capacity=min(1.,weighted_length*o['graphDaylightDepth']/max(1e-9,area))
        # Only the realized adapter creates whole glazed-edge candidates.
        candidates=self.facade_candidates(i,qualified,sky,obstacles) if self.build_candidates and i.nodes[0].cell_type.value=='room' else []
        opportunities=[]
        if i.nodes[0].cell_type.value=='room' and not self.build_candidates:
            # Scalar frontage budgets per observed direction, not window strips.
            groups={}
            for k in range(len(weights)):
                normal_key=tuple(np.round(directions[k],7));groups.setdefault(normal_key,[]).append(k)
            for normal,indices in groups.items():
                if not np.all(qualified[indices]):continue
                w=weights[indices];length=float(w.sum())
                opportunities.append(dict(occurrenceId=oid,floor=floor,normal=list(normal),length=length,
                    estimatedPoint=np.average(origins[indices],axis=0,weights=w).tolist(),
                    skyShare=float(np.average(sky[indices],weights=w))))
        room=dict(nodeIds=[n.node_id for n in i.nodes if n.floor_index==floor],occurrenceId=oid,
            function=i.nodes[0].cell_type.value,area=area,exposedLength=exposed_length,qualifiedFacadeLength=qualified_length,
            skyWeightedFacadeLength=weighted_length,daylightAccessProxy=capacity,
            exposureDeficit=max(0.,o['graphMinRoomExposure']-capacity)/max(1e-9,o['graphMinRoomExposure']),
            narrowFacingLength=float(weights@(exposed&(clearance<o['graphFacadeClearance']))),
            poorVoidFacingLength=float(weights@(exposed&((clearance<o['graphFacadeClearance'])|((sky<o['graphMinSkyShare'])&(clearance<o['graphExposureHorizon']))))),
            lowSkyFacingLength=float(weights@(exposed&(sky<o['graphMinSkyShare']))),
            minimumFacingClearance=float(np.min(clearance[exposed])) if np.any(exposed) else None,
            evidence='implicit_shared_supports',unknownWindows=not self.build_candidates,unobservedBoundary=shape.prior_boundary,
            windowCandidates=candidates,facadeOpportunities=opportunities)
        relations=[]
        for other in sorted(set(nearest[exposed])- {''}):
            selected=exposed&(nearest==other)
            relations.append(dict(u=oid,v=other,relation='open_space_proximity',floor=floor,
                estimatedClearance=float(np.min(clearance[selected])),facingLength=float(weights@selected)))
        self.relations[(oid,floor)]=relations
        # Keep only the latest local result rather than one large key per step.
        self.cache[key]=(signature,room)
        return room

    def window_plan(self,floor):
        from graph_windows import required_frontage
        if self.build_candidates:
            from graph_windows import allocate
        else:
            from graph_window_proxy import allocate
        # One allocation per unchanged floor, shared by metrics and every room.
        key=tuple((i.id,i.origin,i.angle,tuple(n.floor_index for n in i.nodes),i.nodes[0].cell_type.value,
                   shape_token(self.bank.shapes[i.prototype])) for i in self.bank.instances.values())
        cached=getattr(self,'window_cache',{}).get(floor)
        if cached and cached[0]==key:return cached[1]
        instances=[i for i in self.bank.instances.values() if any(n.floor_index==floor for n in i.nodes) and i.nodes[0].cell_type.value!='void']
        rows=[self.measure(i.id,floor) for i in instances]
        required={row['occurrenceId']:required_frontage(row['area'],self.options['graphWindowFrontage'],self.options['graphWindowReferenceArea'])
                  for row in rows if row['function']=='room'}
        result=allocate([c for row in rows for c in row['windowCandidates' if self.build_candidates else 'facadeOpportunities']],required,
                        self.options['graphWindowSeparation'],self.options['graphWindowCone'])
        result['required']=required
        # All occupied facades count, even blank cores. This separate diagnostic
        # cannot be evaded by deleting windows or changing a room to a core.
        exposed=sum(row['exposedLength'] for row in rows)
        narrow=sum(row['poorVoidFacingLength'] for row in rows)
        result['creviceFraction']=narrow/exposed if exposed else 0.
        if not hasattr(self,'window_cache'):self.window_cache={}
        self.window_cache[floor]=(key,result)
        return result

    def occurrence(self,oid,floor,plan=None):
        if self.bank.instances[oid].nodes[0].cell_type.value!='room':return None
        row=self.measure(oid,floor);plan=self.window_plan(floor) if plan is None else plan
        required=plan['required'][oid];frontage=plan['frontage'].get(oid,0.)
        row.update(requiredWindowFrontage=required,windowFrontage=frontage,
                   windowFrontageDeficit=max(0.,1-frontage/required),exposureDeficit=max(0.,1-frontage/required),
                   windows=[w for w in plan['windows'] if w['occurrenceId']==oid])
        return row

    def metrics(self,floor):
        plan=self.window_plan(floor)
        rows=[self.occurrence(oid,floor,plan) for oid,i in self.bank.instances.items()
              if i.nodes[0].cell_type.value=='room' and any(n.floor_index==floor for n in i.nodes)]
        total=sum(row['area'] for row in rows)
        occupied=sum(self.bank.shapes[i.prototype].area for i in self.bank.instances.values()
                     if i.nodes[0].cell_type.value!='void' and any(n.floor_index==floor for n in i.nodes))
        residential_share=total/occupied if occupied else 0.
        from graph_proxy import site_net_area
        boundary=getattr(self.graph,'site_boundaries',{}).get(floor)
        site_area=site_net_area(dict(outer=boundary,holes=getattr(self.graph,'site_holes',{}).get(floor,[]))) if boundary else None
        fill=occupied/site_area if site_area else None
        fill_deficit=max(0.,1.-fill/self.options['graphMinFill']) if fill is not None else 1.
        program_deficit=max(0.,self.options['graphMinResidentialShare']-residential_share)/self.options['graphMinResidentialShare']
        cores=[i for i in self.bank.instances.values() if i.nodes[0].cell_type.value=='core' and any(n.floor_index==floor for n in i.nodes)]
        eligible=[i for i in cores if core_eligible(self.bank.shapes[i.prototype],self.options)]
        capacity=len(eligible)*self.options['graphCoreCapacity']
        capacity_deficit=max(0.,total-capacity)/max(1.,total)
        core_geometry_deficit=(len(cores)-len(eligible))/max(1,len(cores))
        proxy=sum(row['area']*row['daylightAccessProxy'] for row in rows)/total if total else None
        deficit=sum(row['area']*row['exposureDeficit'] for row in rows)/total if total else 0.
        worst_window=max((row['windowFrontageDeficit'] for row in rows),default=0.)
        if worst_window>1e-6:deficit=max(2e-6,deficit)
        distances=access_distances(self.graph,floor);limit=self.options['graphMaxAccessDistance']
        travel_deficit=sum(row['area']*min(1.,max(0.,distances.get(row['nodeIds'][0],math.inf)/limit-1.)) for row in rows)/total if total else 0.
        maximum=max((distances.get(row['nodeIds'][0],math.inf) for row in rows),default=0.)
        crevice_deficit=max(0.,plan['creviceFraction']-self.options['graphMaxCreviceFraction'])
        return dict(daylightAccessProxy=proxy,livableAreaEvaluated=total,livableOccurrencesEvaluated=len(rows),
            daylightDeficit=deficit,accessDistanceDeficit=travel_deficit,
            windowFrontageRatio=sum(min(row['windowFrontage'],row['requiredWindowFrontage']) for row in rows)/max(1e-9,sum(row['requiredWindowFrontage'] for row in rows)),
            windowFrontageDeficit=deficit,roomsMeetingWindowRule=sum(row['windowFrontageDeficit']<=1e-6 for row in rows),
            worstWindowFrontageDeficit=worst_window,
            creviceDeficit=crevice_deficit,creviceFraction=plan['creviceFraction'],
            windowPlan={k:v for k,v in plan.items() if k!='frontage'},
            residentialProgramDeficit=program_deficit,residentialShare=residential_share,
            fillDeficit=fill_deficit,occupiedSiteFill=fill,
            coreCapacityDeficit=capacity_deficit,coreGeometryDeficit=core_geometry_deficit,
            narrowFacingLength=sum(row['narrowFacingLength'] for row in rows),
            maximumEstimatedAccessDistance=maximum if math.isfinite(maximum) else None,
            coreOccurrences=len({i.id for i in self.bank.instances.values() if i.nodes[0].cell_type.value=='core' and any(n.floor_index==floor for n in i.nodes)}),
            coreOccurrenceIds=[i.id for i in cores],
            spatialDeficit=max(deficit,travel_deficit,program_deficit,capacity_deficit,core_geometry_deficit,fill_deficit,crevice_deficit),
            spatialRequirementsMet=bool(rows and max(deficit,travel_deficit,program_deficit,capacity_deficit,core_geometry_deficit,fill_deficit,crevice_deficit)<=1e-6),
            daylightEvidenceStatus='realized_window_intervals_checked' if self.build_candidates else 'graph_frontage_privacy_proxy',
            daylightObligationFunctions=['room'],environmentalComplianceVerified=False,
            rooms=rows)


def evidence(bank):
    options=settings(bank.graph)
    current=getattr(bank,'spatial_evidence',None)
    if current is None or current.options!=options:
        current=bank.spatial_evidence=SpatialEvidence(bank)
    return current


def core_eligible(shape,options):
    if shape.area<options['graphMinCoreArea']-1e-6:return False
    key=('core_width',options['graphMinCoreWidth'])
    if key not in shape.continuity_cache:
        shape.continuity_cache[key]=min(shape.support((nx,ny))+shape.support((-nx,-ny)) for _,nx,ny,*_ in shape.faces)>=options['graphMinCoreWidth']-1e-6
    return shape.continuity_cache[key]


def summary(per_floor):
    rows=list(per_floor)
    if not rows or not all('spatialDeficit' in row for row in rows):return {}
    area=sum(row['livableAreaEvaluated'] for row in rows)
    return dict(daylightAccessProxy=sum(row['livableAreaEvaluated']*(row['daylightAccessProxy'] or 0.) for row in rows)/area if area else None,
        windowFrontageRatio=sum(row['livableAreaEvaluated']*row['windowFrontageRatio'] for row in rows)/area if area else None,
        livableAreaEvaluated=area,spatialDeficit=max(row['spatialDeficit'] for row in rows),
        spatialRequirementsMet=all(row['spatialRequirementsMet'] for row in rows),
        coreOccurrences=len({oid for row in rows for oid in row.get('coreOccurrenceIds',[])}),
        spatialPerFloor=[{k:row.get(k) for k in ('floorIndex','daylightAccessProxy','livableAreaEvaluated',
            'daylightDeficit','windowFrontageDeficit','windowFrontageRatio','roomsMeetingWindowRule','creviceDeficit','creviceFraction','accessDistanceDeficit','residentialProgramDeficit','residentialShare','fillDeficit','occupiedSiteFill',
            'coreCapacityDeficit','coreGeometryDeficit','maximumEstimatedAccessDistance','coreOccurrences',
            'spatialDeficit','spatialRequirementsMet')} for row in rows],
        daylightEvidenceStatus=rows[0].get('daylightEvidenceStatus'),daylightObligationFunctions=['room'],
        environmentalComplianceVerified=False)


def constrained_reward(score,graph_valid,deficit):
    """Feasibility tier precedes design score; deficit gives graded learning.

    No finite fill/reuse improvement can buy a violated spatial requirement.
    Basic graph invalidity remains -1. Every spatial-feasible return is positive.
    """
    if not graph_valid:return -1.
    if deficit>1e-6:return -.01-.98*min(1.,deficit)
    return .01+.98*(math.tanh(score/100.)+1.)/2


def candidate_features(bank,plan,function,distances,anchor=None):
    """Cheap local relation evidence, not a completed exposure measurement."""
    o=settings(bank.graph);shape=plan.shapes.get(plan.prototype,bank.shapes.get(plan.prototype))
    route=distances.get(anchor,0.)+math.dist((plan.x,plan.y),bank.graph.nodes[anchor].pos2d) if anchor in bank.graph.nodes else 0.
    contact_ids={nid for f,nid,_ in plan.contacts if f==plan.floor}
    gaps=[]
    near=bank.spatial.near(plan.floor,plan.x,plan.y)
    for n in near:
        if n.node_id in contact_ids:continue
        other=bank.instances.get(n.metadata.get('root_id',n.node_id))
        if other is None:continue
        dx,dy=n.x-plan.x,n.y-plan.y;d=math.hypot(dx,dy)
        if d<1e-8:continue
        u=(dx/d,dy/d)
        a=rotate(*u,-plan.angle);b=rotate(-u[0],-u[1],-other.angle)
        gaps.append(d-shape.support(a)-bank.shapes[other.prototype].support(b))
    key=(len(bank.graph.nodes),getattr(bank.graph,'function_revision',0),plan.floor)
    cached=getattr(bank,'_spatial_choice_cache',None)
    if cached is None or cached[0]!=key:
        floor_rooms=sum(bank.shapes[i.prototype].area for i in bank.instances.values()
                        if i.nodes[0].cell_type.value=='room' and any(n.floor_index==plan.floor for n in i.nodes))
        cores=sum(i.nodes[0].cell_type.value=='core' and any(n.floor_index==plan.floor for n in i.nodes) for i in bank.instances.values())
        bank._spatial_choice_cache=(key,floor_rooms,cores)
    _,floor_rooms,cores=bank._spatial_choice_cache
    return [float(function=='core'),min(3.,route/o['graphMaxAccessDistance']),
            max(-1.,min(2.,min(gaps,default=o['graphExposureHorizon'])/o['graphFacadeClearance'])),
            shape.area/(max(1e-6,sum(hi-lo for _,_,_,_,_,_,_,_,lo,hi in shape.faces))*o['graphDaylightDepth']),
            min(2.,floor_rooms/max(1.,cores*o['graphCoreCapacity'])),
            bank.graph.num_floors*bank.graph.floor_height/o['graphExposureHorizon']]
