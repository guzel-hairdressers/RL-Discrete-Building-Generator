"""Independent realized-facade measurement of the same architectural proxy.

Actual polygon edges and ray/segment intersections replace numeric support slabs.
This validates graph prediction, not illuminance, windows or code compliance.
Only called on explicit realization, never during graph training.
"""
import math
import numpy as np
from graph_spatial import SpatialEvidence

class RealizedSpatialEvidence(SpatialEvidence):
    def __init__(self,solution):
        super().__init__(solution.graph.module_bank)
        self.polygons={oid:np.asarray(solution.polygon(oid),dtype=float) for oid in solution.occurrences}
        self.surface_cache={};self.edge_cache={}

    def occurrence(self,oid,floor):
        room=super().occurrence(oid,floor)
        if room is not None:room['evidence']='realized_polygon_edges'
        return room

    def intersect_many(self,instances,origins,directions):
        rows=[self.intersect(i,origins,directions) for i in instances]
        return (np.asarray([a for a,b in rows]),np.asarray([b for a,b in rows]))

    def surface(self,instance):
        if instance.id in self.surface_cache:return self.surface_cache[instance.id]
        raw=self.polygons[instance.id]
        area=abs(float(np.sum(raw[:,0]*np.roll(raw[:,1],-1)-raw[:,1]*np.roll(raw[:,0],-1))))/2
        # Coalesce straight boundary fragments for subdivision-invariant sampling.
        # Actual footprints/intersections/area are retained at full precision.
        poly=list(raw)
        changed=True
        while changed and len(poly)>3:
            changed=False
            for k,b in enumerate(poly):
                a=poly[k-1];c=poly[(k+1)%len(poly)];u=b-a;v=c-b
                if abs(u[0]*v[1]-u[1]*v[0])<=1e-7*max(1e-12,math.hypot(*u)*math.hypot(*v)) and float(u@v)>=0:
                    poly.pop(k);changed=True;break
        poly=np.asarray(poly);rows=[]
        for a,b in zip(poly,np.roll(poly,-1,axis=0)):
            dx,dy=b-a;length=math.hypot(dx,dy)
            if length<1e-8:continue
            count=max(1,math.ceil(length/self.options['graphExposureSampleSpacing']-1e-8))
            for j in range(count):
                point=a+(j+.5)/count*(b-a)
                rows.append((*point,dy/length,-dx/length,length/count))
        table=np.asarray(rows)
        result=table[:,:2],table[:,2:4],table[:,4],area
        self.surface_cache[instance.id]=result
        return result

    def intersect(self,instance,origins,directions):
        if instance.id not in self.edge_cache:
            poly=self.polygons[instance.id]
            self.edge_cache[instance.id]=(poly,np.roll(poly,-1,axis=0)-poly)
        starts,edges=self.edge_cache[instance.id]
        delta=starts[None,:,:]-origins[:,None,:]
        det=directions[:,0,None]*edges[None,:,1]-directions[:,1,None]*edges[None,:,0]
        t=np.divide(delta[:,:,0]*edges[None,:,1]-delta[:,:,1]*edges[None,:,0],det,
                    out=np.full_like(det,np.inf),where=np.abs(det)>1e-10)
        u=np.divide(delta[:,:,0]*directions[:,1,None]-delta[:,:,1]*directions[:,0,None],det,
                    out=np.full_like(det,np.inf),where=np.abs(det)>1e-10)
        valid=(t>=-1e-6)&(u>=-1e-7)&(u<=1+1e-7)&np.isfinite(t)
        first=np.min(np.where(valid,np.maximum(0.,t),np.inf),axis=1)
        last=np.max(np.where(valid,np.maximum(0.,t),-np.inf),axis=1)
        # Higher-floor projections can cover the source facade in plan. The ray
        # starts inside that upper footprint, so its entry is0, not its first exit.
        ends=starts+edges
        crosses=(starts[None,:,1]>origins[:,None,1])!=(ends[None,:,1]>origins[:,None,1])
        x_cross=starts[None,:,0]+np.divide(edges[None,:,0]*(origins[:,None,1]-starts[None,:,1]),edges[None,:,1],
            out=np.zeros_like(t),where=np.abs(edges[None,:,1])>1e-12)
        inside=np.sum(crosses&(origins[:,None,0]<x_cross),axis=1)%2==1
        fractions=np.divide(-np.sum(delta*edges[None,:,:],axis=2),np.sum(edges*edges,axis=1)[None,:],
            out=np.zeros_like(t),where=np.sum(edges*edges,axis=1)[None,:]>1e-20)
        closest=delta+np.clip(fractions,0.,1.)[:,:,None]*edges[None,:,:]
        on=np.min(np.sum(closest*closest,axis=2),axis=1)<=1e-12
        first=np.where(inside|on,0.,first)
        last=np.where(inside|on,np.maximum(0.,last),last)
        return first,last


def audit_spatial(solution):
    evaluator=RealizedSpatialEvidence(solution)
    per_floor={f:evaluator.metrics(f) for f in range(solution.graph.num_floors)}
    predicted=getattr(solution.graph.module_bank,'spatial_evidence',None)
    errors={}
    if predicted is not None:
        for f,actual in per_floor.items():
            estimate=predicted.metrics(f)
            errors[f]={key:(estimate[key]-actual[key] if estimate[key] is not None and actual[key] is not None else None)
                       for key in ('daylightAccessProxy','daylightDeficit','narrowFacingLength')}
    return dict(status='realized_proxy_checked',perFloor=per_floor,predictionErrors=errors,
        requirementsMet=all(row['spatialRequirementsMet'] for row in per_floor.values()),
        environmentalComplianceVerified=False,actualIlluminance=None,
        missingEvidence=['window_positions','glazing','materials','climate_sky','external_context_obstructions'])
