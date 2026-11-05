"""Opt-in research ablations. No release defaults, rewards or UI settings change.

Geometry certificates use implicit support inequalities, not room polygons.
Repair is bounded reference search (not a learned repair policy). Every trial's
copy/rebuild/check cost is part of the measured rollout.
"""
from collections import Counter, defaultdict
import copy
import math
import random
import time

import torch
from torch import nn

from graph_policy import GraphActorCritic, GraphLearner
from graph_dictionary import GraphDictionary, Instance, displacement_plane, make_shape, rotate, shape_with
from graph_proxy import SpatialNodes, origin_fits, root_id
from graph_sampler import GraphSeedSampler
from relative_vocabulary import RelativeVocabulary


ARMS = ('baseline', 'boundary', 'ranking', 'repair', 'site_certificate')


def points(poly):
    return [(float(p['x']),float(p['y'])) if isinstance(p,dict) else tuple(p) for p in poly]


def boundary_features(graph, device, enabled=True):
    """Intrinsic, handed local boundary evidence and explicit experiment goals.

    Full-height nodes see their own floor, and the pooled critic sees all floors.
    No absolute compass axes or held-out measurements enter these features.
    """
    rows=[];r=graph.size_prior.radius
    goal=getattr(graph,'research_goal',dict(target=10,maximum=15,fill=1.,rentable=.65))
    for node in graph.nodes.values():
        if not enabled:
            rows.append([0.]*16);continue
        boundary=points(graph.site_boundaries[node.floor_index])
        holes=[points(h) for h in graph.site_holes.get(node.floor_index,())]
        nearest=None;perimeter=0.
        for loop in [boundary,*holes]:
            for a,b in zip(loop,loop[1:]+loop[:1]):
                dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
                if length<1e-12:continue
                t=max(0.,min(1.,((node.x-a[0])*dx+(node.y-a[1])*dy)/(length*length)))
                v=(a[0]+t*dx-node.x,a[1]+t*dy-node.y)
                perimeter+=length
                distance=math.hypot(*v)
                if nearest is None or distance<nearest[0]:nearest=(distance,v,(dx/length,dy/length),float(loop is not boundary))
        ref=RelativeVocabulary.reference_angle(graph.module_bank,node)
        distance,v,tangent,is_hole=nearest
        vx,vy=rotate(v,-ref);tx,ty=rotate(tangent,-ref)
        def area(loop):return abs(sum(x*v-y*u for (x,y),(u,v) in zip(loop,loop[1:]+loop[:1])))/2
        site_area=area(boundary)-sum(area(h) for h in holes)
        corner=min(math.hypot(x-node.x,y-node.y) for loop in [boundary,*holes] for x,y in loop)
        rows.append([distance/r,vx/(2*r),vy/(2*r),tx,ty,is_hole,corner/r,
            math.log1p(site_area/(r*r))/5,perimeter/(100*r),len(holes)/4,
            float(GraphSeedSampler._point_inside_polygon((node.x,node.y),boundary)),
            goal['target']/15,goal['maximum']/15,goal['fill'],goal['rentable'],len(boundary)/32])
    return torch.tensor(rows,dtype=torch.float32,device=device)


class BoundaryActorCritic(GraphActorCritic):
    def __init__(self):
        super().__init__()
        self.boundary=nn.Sequential(nn.Linear(16,32),nn.SiLU(),nn.Linear(32,32))
        nn.init.zeros_(self.boundary[-1].weight);nn.init.zeros_(self.boundary[-1].bias)
        self.boundary_input=None

    def encode(self,*args):
        h,_=super().encode(*args)
        # All arms have identical parameter capacity. The control sees zeros;
        # the boundary arm alone receives the site's measured descriptors.
        h=h+self.boundary(self.boundary_input)
        return h,h.mean(0)


class ResearchLearner(GraphLearner):
    def __init__(self,seed=123,boundary=False,lr=.001):
        super().__init__(seed=seed,lr=lr)
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(seed)
            self.model=BoundaryActorCritic().to(self.device)
        self.optimizer=torch.optim.Adam(self.model.parameters(),lr=lr)
        self.boundary_enabled=boundary
        self._boundary_cache=None
        self.inference_sampling=False

    def _prepare(self,graph):
        key=(id(graph),len(graph.nodes))
        if self._boundary_cache is None or self._boundary_cache[0]!=key:
            self._boundary_cache=(key,boundary_features(graph,self.device,self.boundary_enabled))
        self.model.boundary_input=self._boundary_cache[1]
        return super()._prepare(graph)

    def invalidate(self):
        self._prepared=None;self._boundary_cache=None

    def state(self):
        result=super().state()
        # Deliberately not accepted by the production checkpoint loader.
        result.update(schema='research-boundary-1',boundaryEnabled=self.boundary_enabled)
        return result

    def load_research(self,state):
        if state.get('schema')!='research-boundary-1':raise ValueError('not a research checkpoint')
        self.model.load_state_dict(state['model']);self.optimizer.load_state_dict(state['optimizer'])
        self.rng.set_state(state['rng']);self.updates=state['updates']
        self.boundary_enabled=state['boundaryEnabled'];self.clear_episode();self.invalidate()

    def choose(self,graph,features,training=True,**kwargs):
        if training or not self.inference_sampling:return super().choose(graph,features,training,**kwargs)
        # Frozen stochastic alternatives: selection explores, but no trajectory,
        # gradients or optimizer updates are created.
        with torch.no_grad():
            tensors,encoded=self._prepare(graph)
            logits,_=self.model(*tensors,torch.tensor(features,dtype=torch.float32,device=self.device),encoded=encoded)
            index=int(torch.multinomial(logits.softmax(0).cpu(),1,generator=self.rng))
        self._prepared=None
        return index


def shape_inside_site(shape,origin,angle,boundary,holes=()):
    """Exact convex support/segment certificate, including concavities and holes.

    A convex shape contains its stable origin. If that origin is in the site and
    no site/hole segment enters its strict interior, the whole shape is inside.
    No vertices, clipping, polygon Boolean operations or GEOS are used.
    """
    loops=[points(boundary),*[points(h) for h in holes]]
    if not GraphSeedSampler._point_inside_polygon(origin,loops[0]):return False
    if any(GraphSeedSampler._point_inside_polygon(origin,h) for h in loops[1:]):return False
    faces=[(nx,ny,b) for _,nx,ny,b,*_ in shape.faces]
    for loop in loops:
        for a,b in zip(loop,loop[1:]+loop[:1]):
            ax,ay=rotate((a[0]-origin[0],a[1]-origin[1]),-angle)
            bx,by=rotate((b[0]-origin[0],b[1]-origin[1]),-angle)
            lo,hi=0.,1.
            for nx,ny,bound in faces:
                value=nx*ax+ny*ay-(bound-1e-7)
                slope=nx*(bx-ax)+ny*(by-ay)
                if abs(slope)<1e-12:
                    if value>=0:hi=-1.;break
                elif slope>0:hi=min(hi,-value/slope)
                else:lo=max(lo,-value/slope)
                if lo>=hi:break
            if lo<hi:return False
    return True


def implicit_score(bank,site_areas,target=10):
    from graph_proxy import GraphSketch
    sketch=GraphSketch(bank.graph)
    # Match the actual per-floor terminal objective. The first pilot used a
    # building-wide ratio surrogate here; its snapshots/results are retained and
    # explicitly labeled. A ratio of sums is correct for displayed fill, but it
    # is not the same as this mean of per-floor nonlinear objective scores.
    return sum(sketch.metrics(f,site_areas[f],target)['score'] for f in range(bank.graph.num_floors))/bank.graph.num_floors


def restore_dictionary(solution,max_types=15):
    """Restore a frozen baseline for matched-state repair diagnostics, no learning."""
    graph=solution.graph;graph.size_prior=solution.prior
    bank=GraphDictionary.__new__(GraphDictionary)
    bank.graph=graph;bank.prior=solution.prior;bank.max_types=max_types
    bank.instances={oid:Instance(oid,o.nodes,o.prototype,o.angle) for oid,o in solution.occurrences.items()}
    bank.members=defaultdict(set);bank.floor_nodes=defaultdict(list);bank.copy_counts=Counter()
    bank.incident=defaultdict(list);bank.links=defaultdict(set);required=defaultdict(set)
    for oid,i in bank.instances.items():
        bank.members[i.prototype].add(oid);bank.copy_counts[i.prototype]+=len(i.nodes)
        for n in i.nodes:bank.floor_nodes[n.floor_index].append(n)
    for edge in graph.edges_horiz:
        a,b=(bank.instances[root_id(graph.nodes[nid])] for nid in (edge.u,edge.v))
        for first,second in ((a,b),(b,a)):
            displacement=(second.origin[0]-first.origin[0],second.origin[1]-first.origin[1])
            required[first.prototype].add(displacement_plane(displacement,first.angle))
            bank.incident[first.prototype].append(edge)
            dx,dy=rotate(displacement,-first.angle)
            bank.links[first.prototype].add((dx,dy,second.prototype,second.angle-first.angle))
    bank.spatial=SpatialNodes(graph,bank.prior.radius);evidence=defaultdict(set)
    # Replay metric observations directly. Recovering normals from tiny polygon
    # edges amplifies roundoff and is not a faithful dictionary reconstruction.
    for node in graph.nodes.values():
        instance=bank.instances[root_id(node)]
        for other in bank.spatial.near(node.floor_index,node.x,node.y):
            if node.node_id!=other.node_id:
                evidence[instance.prototype].add(displacement_plane((other.x-node.x,other.y-node.y),instance.angle))
    bank.shapes={pid:make_shape(tuple(sorted(evidence[pid])),frozenset(required[pid]),bank.prior)
        for pid in solution.prototypes}
    if any(s is None for s in bank.shapes.values()):raise ValueError('frozen prototype reconstruction failed')
    bank.spatial=SpatialNodes(graph,bank.prior.radius);bank.rejections=Counter();bank._distance_index=None
    bank.initial_fits={f:all(origin_fits((n.x,n.y),graph.site_boundaries[f],graph.site_holes[f],bank.prior.radius) for n in nodes)
        for f,nodes in bank.floor_nodes.items()}
    bank.vocabulary=RelativeVocabulary();bank.vocabulary.observe(graph,list(graph.nodes))
    graph.module_bank=bank;bank.view();return graph


def rebuild_after_pose(original,oid,position,angle):
    """Transactional implicit reconstruction, fixed identities, joint footprints.

    The previous geometry is NOT trusted after a move. All nearby separating
    constraints are repooled in prototype frames; contacts and access rebuilt.
    This deliberately conservative first repair implementation includes its
    full copy/rebuild cost in experiments.
    """
    graph=copy.deepcopy(original);bank=graph.module_bank
    instance=bank.instances[oid]
    for node in instance.nodes:node.x,node.y=position;node.orientation=angle
    instance.angle=angle
    bank.spatial=SpatialNodes(graph,bank.prior.radius)
    evidence=defaultdict(set);pairs=[];seen=set()
    for node in graph.nodes.values():
        current=bank.instances[root_id(node)]
        if not origin_fits((node.x,node.y),graph.site_boundaries[node.floor_index],
            graph.site_holes[node.floor_index],bank.prior.radius):return None
        for other in bank.spatial.near(node.floor_index,node.x,node.y):
            if node.node_id==other.node_id:continue
            if math.dist((node.x,node.y),(other.x,other.y))<2.5-1e-8:return None
            evidence[current.prototype].add(displacement_plane((other.x-node.x,other.y-node.y),current.angle))
            key=tuple(sorted((node.node_id,other.node_id)))
            if key not in seen:seen.add(key);pairs.append(key)
    shapes={pid:make_shape(tuple(sorted(evidence[pid])),frozenset(),bank.prior) for pid in bank.shapes}
    if any(s is None for s in shapes.values()):return None
    graph.edges_horiz=[];graph._adj_horiz={nid:set() for nid in graph.nodes}
    bank.incident=defaultdict(list);bank.links=defaultdict(set);requirements=defaultdict(set)
    for u,v in pairs:
        a,b=graph.nodes[u],graph.nodes[v]
        ia,ib=bank.instances[root_id(a)],bank.instances[root_id(b)]
        length=bank.contact(ia.origin,shapes[ia.prototype],ia.angle,ib.origin,shapes[ib.prototype],ib.angle)
        if length<bank.prior.min_contact-1e-6:continue
        edge=graph.add_edge(u,v,shared_length=length,properties={'relation':'construction','constraint_checked':True,'validated':False})
        for first,second in ((ia,ib),(ib,ia)):
            bank.incident[first.prototype].append(edge)
            dx,dy=second.origin[0]-first.origin[0],second.origin[1]-first.origin[1]
            requirements[first.prototype].add(displacement_plane((dx,dy),first.angle))
            rx,ry=rotate((dx,dy),-first.angle)
            bank.links[first.prototype].add((rx,ry,second.prototype,second.angle-first.angle))
    if not graph.validate_circulation_connectivity():return None
    for pid,shape in shapes.items():
        shapes[pid]=shape_with(shape,(),requirements[pid],bank.prior)
        if shapes[pid] is None:return None
    bank.shapes=shapes;bank._distance_index=None
    bank.vocabulary=RelativeVocabulary();bank.vocabulary.observe(graph,list(graph.nodes))
    bank.view()
    return graph


class GraphExperiment:
    def __init__(self,arm='baseline',seed=123,training=True,ranker=None):
        if arm not in ARMS:raise ValueError('unknown ablation')
        self.arm=arm;self.seed=seed;self.training=training
        self.exact_site=arm=='site_certificate';self.choice_limit=4 if arm=='ranking' else 12
        self.counters=Counter();self.seconds=Counter();self.observations=[];self.repair_log=[]
        self.ranker=ranker or FeasibilityRanker(seed)
        self._features={};self._repair_attempts=0

    def candidate_features(self,bank,f,candidate):
        key=(len(bank.graph.nodes),f,id(candidate))
        if key not in self._features:
            x,y=candidate['x'],candidate['y'];near=bank.spatial.near(f,x,y);r=bank.prior.radius
            boundary=points(bank.graph.site_boundaries[f])
            from typed_cell import BuildingGraph
            self._features[key]=[1.,min((math.dist((x,y),(n.x,n.y)) for n in near),default=2*r)/(2*r),
                len(near)/12,candidate.get('span',0)/(2*r),float('preferredPrototype' in candidate),
                BuildingGraph._min_distance_to_boundary((x,y),boundary)/(2*r),len(bank.shapes)/bank.max_types,
                float(candidate.get('source')=='shared_module_contact')]
        return self._features[key]

    def rank(self,bank,f,candidates):
        self.counters['candidatesGenerated']+=len(candidates)
        self._features={}
        if self.arm!='ranking':return candidates
        stamp=time.perf_counter()
        features=[self.candidate_features(bank,f,c) for c in candidates]
        with torch.no_grad():scores=self.ranker.model(torch.tensor(features,dtype=torch.float32)).flatten().tolist()
        result=[c for _,c in sorted(zip(scores,candidates),key=lambda pair:-pair[0])]
        self.seconds['ranking']+=time.perf_counter()-stamp
        return result

    def observe(self,bank,f,candidate,accepted,site_rejected=False):
        self.counters['testedCandidates']+=1
        self.counters['positiveCandidates']+=int(accepted)
        self.counters['radiusRejected']+=int(site_rejected)
        if self.arm=='ranking' and self.training:
            self.observations.append((self.candidate_features(bank,f,candidate),float(accepted)))

    def filter_plans(self,bank,plans,certified):
        if certified or not self.exact_site:return plans
        stamp=time.perf_counter();accepted=[]
        for plan in plans:
            self.counters['shapeSiteTests']+=1
            floors=range(bank.graph.num_floors) if plan.scope=='multi_floor' else (plan.floor,)
            if all(shape_inside_site(plan.shapes[plan.prototype],(plan.x,plan.y),plan.angle,
                bank.graph.site_boundaries[f],bank.graph.site_holes[f]) for f in floors):accepted.append(plan)
        self.counters['radiusRejectedButShapeFits']+=len(accepted)
        self.seconds['siteCertificate']+=time.perf_counter()-stamp
        return accepted

    def finish(self):
        if self.training and self.observations:self.ranker.update(self.observations)
        return dict(counters=dict(self.counters),seconds=dict(self.seconds),repairTrials=self.repair_log)

    def repair(self,trainer,stalled):
        if self.arm!='repair' or self._repair_attempts>=6:return False
        if not stalled and (trainer.graph_step_count+1)%8:return False
        stamp=time.perf_counter();bank=trainer.building_graph.module_bank
        from graph_proxy import site_net_area
        area={env.index:site_net_area(env.site) for env in trainer.environments}
        before=implicit_score(bank,area,trainer.settings['dictCap'])
        rng=random.Random(self.seed+trainer.graph_step_count*104729)
        # Pick low-degree non-core occurrences, not preselected rectangular motifs.
        occurrences=[i for i in bank.instances.values() if i.nodes[0].cell_type.value=='room']
        rng.shuffle(occurrences);occurrences.sort(key=lambda i:sum(len(bank.graph._adj_horiz[n.node_id]) for n in i.nodes))
        accepted=False
        for instance in occurrences[:min(2,6-self._repair_attempts)]:
            self._repair_attempts+=1;self.counters['repairTrials']+=1
            direction=rng.uniform(-math.pi,math.pi);distance=rng.uniform(.05,.35)*bank.prior.radius
            target=(instance.origin[0]+distance*math.cos(direction),instance.origin[1]+distance*math.sin(direction))
            angle=instance.angle+rng.uniform(-.12,.12)
            trial_started=time.perf_counter()
            trial=rebuild_after_pose(trainer.building_graph,instance.id,target,angle)
            after=implicit_score(trial.module_bank,area,trainer.settings['dictCap']) if trial is not None else None
            take=after is not None and after>before+1e-6
            self.repair_log.append(dict(occurrence=instance.id,seconds=time.perf_counter()-trial_started,
                feasible=trial is not None,accepted=take,scoreBefore=before,scoreAfter=after))
            if take:
                trainer.building_graph=trial;bank=trial.module_bank;before=after
                trainer.graph_learner.invalidate();accepted=True;self.counters['repairsAccepted']+=1
        self.seconds['repair']+=time.perf_counter()-stamp
        return accepted


class FeasibilityRanker:
    def __init__(self,seed=123):
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(seed)
            self.model=nn.Linear(8,1)
            nn.init.zeros_(self.model.weight);nn.init.zeros_(self.model.bias)
        self.optimizer=torch.optim.Adam(self.model.parameters(),lr=.02)
        self.updates=0

    def update(self,observations):
        x,y=zip(*observations)
        x=torch.tensor(x,dtype=torch.float32);y=torch.tensor(y,dtype=torch.float32)
        # Online labels come only from training checks. Held-out evaluation is frozen.
        self.optimizer.zero_grad(set_to_none=True)
        loss=nn.functional.binary_cross_entropy_with_logits(self.model(x).flatten(),y)
        loss.backward();self.optimizer.step();self.updates+=1

    def state(self):return dict(model=copy.deepcopy(self.model.state_dict()),optimizer=self.optimizer.state_dict(),updates=self.updates)
