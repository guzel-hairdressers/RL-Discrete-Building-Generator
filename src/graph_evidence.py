"""Uncalibrated spatial estimates with explicit evidence and missing-data states."""
import math


def daylight_accessibility(graph, result, floor):
    """Directional openness/depth proxy. Not illuminance or code compliance."""
    estimates={}
    for oid,o in result.occurrences.items():
        if not o.prototype: continue
        for n in o.nodes:
            if n.floor_index!=floor or n.cell_type.value!='room': continue
            neighbors=[q for q in graph.get_neighbors(n.node_id) if q.cell_type.value!='void']
            angles=sorted(math.atan2(q.y-n.y,q.x-n.x) for q in neighbors)
            gaps=[(angles[(i+1)%len(angles)]-a)%(2*math.pi) for i,a in enumerate(angles)] if len(angles)>1 else [2*math.pi]
            openness=max(gaps)/ (2*math.pi)
            holes=[q for q in graph.get_neighbors(n.node_id) if q.cell_type.value=='void']
            well_evidence=[]
            for hole in holes:
                ho=next((v for v in result.occurrences.values() if hole in v.nodes),None)
                if ho and ho.prototype:
                    p=result.prototypes[ho.prototype]
                    # Compare well span with depth: a tiny well does not imply full daylight.
                    width=2*min((b for normal,b in p.constraints),default=result.prior.radius)
                    well_evidence.append(max(0.,min(1.,width/max(1.,math.dist(o.origin,ho.origin)))))
            estimates[n.node_id]={'value':min(1.,max(openness,max(well_evidence,default=0.))),
                'status':'uncalibrated','evidence':'angular_openness_and_well_span',
                'priorBoundary':result.prototypes[o.prototype].prior_boundary}
    return estimates


def sun_access(origin, height, obstructions, directions):
    """Point-origin directional shadow estimate using footprint segments/heights.

    Directions are explicit (azimuth, altitude) radians in the graph coordinate
    frame. Caller supplies geolocation/time conversion. No directions => unknown.
    """
    if not directions: return {'value':None,'status':'missing_sun_directions'}
    visible=[]
    for az,alt in directions:
        if alt<=0: continue
        ray=(math.cos(az),math.sin(az)); blocked=False
        for building in obstructions:
            pts=building['polygon']; top=building['height']
            for a,b in zip(pts,pts[1:]+pts[:1]):
                ex,ey=b[0]-a[0],b[1]-a[1]
                det=ray[0]*ey-ray[1]*ex
                if abs(det)<1e-10: continue
                ax,ay=a[0]-origin[0],a[1]-origin[1]
                t=(ax*ey-ay*ex)/det
                u=(ax*ray[1]-ay*ray[0])/det
                if t>=0 and 0<=u<=1 and top>=height+t*math.tan(alt): blocked=True
            if blocked: break
        visible.append(not blocked)
    return {'value':sum(visible)/len(visible) if visible else None,
            'status':'uncalibrated' if visible else 'no_above_horizon_samples',
            'evidence':'origin_rays_with_context_heights','sampleCount':len(visible)}
