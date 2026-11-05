"""Frozen-graph realization and circulation experiments, independent of training.

Port inference accepts explicit wall evidence; an embedding alone does not supply
these ports. Reference-derived ports are an oracle capability test, not a learned
port predictor or evidence of better generated layouts.
"""
from collections import defaultdict
from dataclasses import replace
import math
import time

from graph_dictionary import rotate
from shared_modules import (Inference, Occurrence, Prototype, SizePrior, area,
    clip, _bounded_polygon, validate)
from typed_cell import BuildingGraph, GraphNode, CellType, VerticalScope


def xy(poly):return [(p['x'],p['y']) if isinstance(p,dict) else tuple(p) for p in poly]


def from_layout(document):
    event=document['event'];graph=BuildingGraph(len(document['sites']))
    graph.site_boundaries={f:xy(s['outer']) for f,s in enumerate(document['sites'])}
    graph.site_holes={f:[xy(h) for h in s['holes']] for f,s in enumerate(document['sites'])}
    occurrences={};prototypes={};unresolved={}
    for p in event['placements']:
        oid=p.get('moduleStackId',p['id']);pid=p['moduleId'];angle=math.radians(p['rotation'])
        origin=(p['position']['x'],p['position']['y']);nid=p['node_id']
        node=GraphNode(nid,*origin,floor_index=p['floor'],cell_type=CellType(p['category']),
            scope=VerticalScope(p['scope']),module_id=pid,orientation=angle,area=p['area'],
            metadata={'root_id':oid} if nid!=oid else {})
        graph.nodes[nid]=node;graph._adj_horiz[nid]=set();graph._adj_vert[nid]=set()
        if oid not in occurrences:occurrences[oid]=Occurrence(oid,[],angle=angle,prototype=pid)
        occurrences[oid].nodes.append(node)
        local=[rotate((x-origin[0],y-origin[1]),-angle) for x,y in xy(p['poly'])]
        if pid not in prototypes:prototypes[pid]=Prototype(pid,local,[],p.get('priorBoundary',False),[])
        if oid not in prototypes[pid].members:prototypes[pid].members.append(oid)
    for e in event['graphState']['edgesHoriz']:
        if e['u'] in graph.nodes and e['v'] in graph.nodes:graph.add_edge(e['u'],e['v'])
    if event['validation'].get('unresolved'):unresolved.update(event['validation']['unresolved'])
    return Inference(occurrences,prototypes,unresolved,SizePrior(),graph)


def clean_polygon(poly,tolerance=1e-8):
    result=[]
    for p in poly:
        if not result or math.dist(result[-1],p)>tolerance:result.append(p)
    if len(result)>1 and math.dist(result[0],result[-1])<tolerance:result.pop()
    changed=True
    while changed and len(result)>3:
        changed=False
        for i,p in enumerate(result):
            a,b=result[i-1],result[(i+1)%len(result)]
            u=(p[0]-a[0],p[1]-a[1]);v=(b[0]-p[0],b[1]-p[1])
            if abs(u[0]*v[1]-u[1]*v[0])<tolerance*max(1.,math.hypot(*u)*math.hypot(*v)) and u[0]*v[0]+u[1]*v[1]>=0:
                result.pop(i);changed=True;break
    return result


def corner_metrics(poly):
    poly=clean_polygon(poly);weights=[];deviations=[]
    for i,p in enumerate(poly):
        a,b=poly[i-1],poly[(i+1)%len(poly)]
        u=(a[0]-p[0],a[1]-p[1]);v=(b[0]-p[0],b[1]-p[1])
        length=math.hypot(*u)*math.hypot(*v)
        if length<1e-14:continue
        interior=math.acos(max(-1.,min(1.,(u[0]*v[0]+u[1]*v[1])/length)))
        weights.append(math.sqrt(length));deviations.append(abs(interior-math.pi/2))
    total=sum(weights)
    return dict(corners=len(weights),weightedRightFraction=sum(w for w,d in zip(weights,deviations) if d<=math.radians(5))/max(1e-12,total),
        weightedDeviationDegrees=math.degrees(sum(w*d for w,d in zip(weights,deviations))/max(1e-12,total)))


def orthogonal_completion(solution,max_area_loss=.02):
    """Try freely oriented rectangular cuts on shared prototypes, never instances.

    This is a bounded conservative realizer baseline, NOT shape synthesis. All
    observed geometry stays inside its reference footprint, and every required
    positive-length contact must survive. Failed candidates remain counted.
    """
    from shapely.geometry import Polygon
    start=time.perf_counter();prototypes=dict(solution.prototypes);accepted=0;tested=0;contact_failures=0
    current=replace(solution,prototypes=prototypes)
    if max_area_loss==0:
        return current,dict(seconds=time.perf_counter()-start,candidates=0,contactRejected=0,
            changedPrototypes=0,maxAreaLoss=0.,method='zero_loss_control')
    by_node={n.node_id:o for o in solution.occurrences.values() for n in o.nodes}
    for pid,prototype in solution.prototypes.items():
        poly=clean_polygon(prototype.polygon);base=corner_metrics(poly)
        best=(base['weightedRightFraction'],-base['weightedDeviationDegrees'],area(poly));best_poly=poly
        walls=sorted(zip(poly,poly[1:]+poly[:1]),key=lambda ab:-math.dist(*ab))
        angles=list(dict.fromkeys(round(math.atan2(b[1]-a[1],b[0]-a[0])%(math.pi/2),10) for a,b in walls))[:8]
        # Orientations come from actual wall directions; there is no world grid.
        # A continuous refinement around the best observed direction follows.
        def attempt(theta):
            nonlocal best,best_poly,tested,contact_failures
            c,s=math.cos(theta),math.sin(theta);axes=((c,s),(-s,c))
            bounds=[max(nx*x+ny*y for x,y in poly) for nx,ny in (*axes,(-c,-s),(s,-c))]
            normals=(*axes,(-c,-s),(s,-c))
            def cut(scale):
                result=poly
                for normal,bound in zip(normals,bounds):result=clip(result,normal,bound*scale)
                return clean_polygon(result)
            lo,hi=0.,1.;minimum=area(poly)*(1-max_area_loss)
            for _ in range(24):
                mid=(lo+hi)/2
                if area(cut(mid))<minimum:lo=mid
                else:hi=mid
            candidate=cut(hi);tested+=1;metric=corner_metrics(candidate)
            score=(metric['weightedRightFraction'],-metric['weightedDeviationDegrees'],area(candidate))
            if score<=best:return metric['weightedRightFraction']
            prototypes[pid]=replace(prototype,polygon=candidate)
            polygons={}
            feasible=True
            for edge in solution.graph.edges_horiz:
                if pid not in (by_node[edge.u].prototype,by_node[edge.v].prototype):continue
                for nid in (edge.u,edge.v):
                    if nid not in polygons:polygons[nid]=Polygon(current.polygon(by_node[nid].id))
                length=polygons[edge.u].boundary.buffer(1e-6).intersection(polygons[edge.v].boundary).length
                if length<solution.prior.min_contact-1e-7:feasible=False;break
            if feasible:best=score;best_poly=candidate
            else:contact_failures+=1
            prototypes[pid]=replace(prototype,polygon=best_poly)
            return metric['weightedRightFraction'] if feasible else -1.
        for theta in angles:attempt(theta)
        if angles:
            from scipy.optimize import minimize_scalar
            index=max(range(len(angles)),key=lambda j:attempt(angles[j]))
            center=angles[index]
            minimize_scalar(lambda theta:-attempt(theta),bounds=(center-.12,center+.12),method='bounded',options={'maxiter':6})
        if best_poly!=poly:accepted+=1
        prototypes[pid]=replace(prototype,polygon=best_poly)
    return current,dict(seconds=time.perf_counter()-start,candidates=tested,contactRejected=contact_failures,
        changedPrototypes=accepted,maxAreaLoss=max_area_loss,method='bounded_shared_orthogonal_cuts')


def wall_evidence(poly):
    """Explicit canonical support planes, independent of origin-to-origin edges."""
    poly=clean_polygon(poly)
    signed=sum(x*v-y*u for (x,y),(u,v) in zip(poly,poly[1:]+poly[:1]))
    if signed<0:poly=list(reversed(poly))
    result=[]
    for a,b in zip(poly,poly[1:]+poly[:1]):
        dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
        if length>1e-10:
            normal=(dy/length,-dx/length);result.append((normal,normal[0]*a[0]+normal[1]*a[1]))
    return result


def realize_ports(graph,occurrences,evidence,prior):
    """Replaceable convex adapter: pool explicit wall/port evidence by prototype.

    Each item has prototype, local normal, local offset and optional required
    contact status. Negative offsets/origins outside a module are not supported
    by this proof of concept. Non-neighbor separation is checked independently.
    """
    constraints=defaultdict(list);required=defaultdict(list);members=defaultdict(list)
    for item in evidence:
        row=(tuple(item['normal']),float(item['offset']))
        constraints[item['prototype']].append(row)
        if item.get('required'):required[item['prototype']].append(row)
    for oid,o in occurrences.items():members[o.prototype].append(oid)
    prototypes={};unresolved={}
    for pid,ids in members.items():
        polygon=_bounded_polygon(tuple(constraints[pid]),tuple(required[pid]),prior)
        if polygon is None:
            for oid in ids:unresolved[oid]='port evidence infeasible for convex adapter'
        else:
            observed=constraints[pid]
            prior_boundary=any(not any(math.dist(normal,n)<1e-7 and abs(bound-b)<1e-7
                for n,b in observed) for normal,bound in wall_evidence(polygon))
            prototypes[pid]=Prototype(pid,polygon,ids,prior_boundary,observed)
    return Inference(occurrences,prototypes,unresolved,prior,graph)


def public_circulation(solution,min_residential_share=.65):
    """Connected public corridor pieces; each remaining room is its own unit.

    Reuse identities/footprints do not change. This is a post-layout assignment
    experiment, not a trained corridor-growth policy or a code-compliance check.
    Only independent realized positive-length contacts may provide openings.
    """
    from shared_modules import contact_pairs
    start=time.perf_counter();_,contacts=contact_pairs(solution)
    adj={nid:set() for nid in solution.graph.nodes}
    for a,b in contacts:adj[a].add(b);adj[b].add(a)
    node_to_occ={n.node_id:oid for oid,o in solution.occurrences.items() for n in o.nodes}
    nodes={n.node_id:n for n in solution.graph.nodes.values() if n.cell_type!=CellType.VOID}
    cores={nid for nid,n in nodes.items() if n.cell_type==CellType.CORE}
    core_occ={node_to_occ[nid] for nid in cores}
    corridor_occ=set(core_occ)
    def public_nodes(assigned):
        return {n.node_id for oid in assigned for n in solution.occurrences[oid].nodes}
    def served(network):
        return network|set().union(*(adj[n] for n in network)) if network else set()
    while True:
        network=public_nodes(corridor_occ);unserved=set(nodes)-served(network)
        if not unserved:break
        frontier={node_to_occ[nid] for nid in served(network)&set(nodes)}-corridor_occ
        options=[]
        for oid in frontier:
            copies=solution.occurrences[oid].nodes
            # A full-height public occurrence must attach on every floor.
            if not all(adj[n.node_id]&network for n in copies):continue
            gain=sum(len(adj[n.node_id]&unserved) for n in copies)
            if gain:options.append((gain/max(1e-9,sum(n.area for n in copies)),oid))
        if not options:break
        corridor_occ.add(max(options)[1])
    def connected(network):
        seen=set(cores);queue=list(cores)
        for current in queue:
            for other in (adj[current]&network)-seen:seen.add(other);queue.append(other)
        return seen==network
    for oid in sorted(corridor_occ-core_occ,reverse=True):
        trial=corridor_occ-{oid};network=public_nodes(trial)
        if connected(network) and set(nodes)<=served(network):corridor_occ=trial
    network=public_nodes(corridor_occ);unserved=set(nodes)-served(network)
    candidate_doors=[];seen=set(cores);queue=list(cores)
    for current in queue:
        for other in sorted((adj[current]&network)-seen):
            seen.add(other);queue.append(other);candidate_doors.append((current,other))
    for nid in sorted(set(nodes)-network):
        available=sorted(adj[nid]&network)
        if available:candidate_doors.append((nid,available[0]))
    reports=[]
    for floor in range(solution.graph.num_floors):
        floor_nodes={nid:n for nid,n in nodes.items() if n.floor_index==floor}
        public_pieces=(network-cores)&set(floor_nodes)
        residential=set(floor_nodes)-network
        total=sum(n.area for n in floor_nodes.values());rentable=sum(nodes[nid].area for nid in residential)
        corridor_area=sum(nodes[nid].area for nid in public_pieces)
        valid=(not (unserved&set(floor_nodes)) and bool(cores&set(floor_nodes))
            and rentable/max(1e-9,total)>=min_residential_share and connected(network))
        reports.append(dict(floor=floor,valid=valid,unserved=sorted(unserved&set(floor_nodes)),corridorOccurrences=len(public_pieces),
            circulationArea=corridor_area,residentialArea=rentable,residentialShare=rentable/max(1e-9,total),
            minimumResidentialShare=min_residential_share,unitCount=len(residential),
            corridors=sorted(public_pieces),units={nid:[nid] for nid in sorted(residential)}))
    return dict(valid=all(r['valid'] for r in reports),perFloor=reports,scopeConflicts=[],
        candidateDoorContacts=candidate_doors,minimumContactLength=solution.prior.min_contact,
        actualDoorDesignVerified=False,
        seconds=time.perf_counter()-start,method='post_layout_connected_public_corridors',trained=False)
