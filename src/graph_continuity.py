"""Local floor-plate continuity certificates on implicit convex boundaries.

No polygon construction, clipping, Boolean overlay, or final-layout rejection.
For a hole-free connected floor plate, attaching a convex room cannot create a
hole if its intersection with the old plate is one connected boundary arc.
Shared-shape shrinkage must additionally preserve all old multi-room junctions.
The dictionary maintains those junction witnesses transactionally.
"""
import math

TOLERANCE=1e-6


def protected_hull(points):
    """Extreme junction witnesses, not a realized room/floor polygon."""
    points=sorted(set(points))
    if len(points)<=2:return tuple(points)
    def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    lower=[];upper=[]
    for p in points:
        while len(lower)>=2 and cross(lower[-2],lower[-1],p)<=0:lower.pop()
        lower.append(p)
    for p in reversed(points):
        while len(upper)>=2 and cross(upper[-2],upper[-1],p)<=0:upper.pop()
        upper.append(p)
    return tuple(lower[:-1]+upper[:-1])


def boundary_data(shape):
    cache=shape.continuity_cache
    if 'boundary' not in cache:
        start=0.;rows=[]
        for face in shape.faces:
            angle,nx,ny,b,cx,cy,tx,ty,lo,hi=face
            rows.append((face,start));start+=hi-lo
        cache['boundary']=(rows,start)
    return cache['boundary']


def boundary_interval(shape,key):
    """Intersection with a supporting line, retaining point-only contacts too."""
    cache=shape.continuity_cache;token=('line',key)
    if token in cache:return cache[token]
    length=math.hypot(*key[:2]);nx,ny=key[0]/length,key[1]/length;b=key[2]/length
    cx,cy=nx*b,ny*b;tx,ty=-ny,nx;lo=-math.inf;hi=math.inf
    for _,fx,fy,bound,*_ in shape.faces:
        coefficient=fx*tx+fy*ty;residual=bound-fx*cx-fy*cy
        if abs(coefficient)<1e-10:
            if residual < -TOLERANCE:lo=math.inf;break
        elif coefficient>0:hi=min(hi,(residual+TOLERANCE)/coefficient)
        else:lo=max(lo,(residual+TOLERANCE)/coefficient)
    found=None
    if math.isfinite(lo) and math.isfinite(hi) and lo<=hi+1e-7:
        found=(lo,hi) if lo<=hi else ((lo+hi)/2,)*2
    cache[token]=found
    return found


def point_inside(shape,point,tolerance=TOLERANCE):
    x,y=point
    return all(nx*x+ny*y<=b+tolerance for _,nx,ny,b,*_ in shape.faces)


def arc_position(shape,key,value):
    """Map a support-line coordinate onto the perimeter's circular coordinate."""
    rows,total=boundary_data(shape)
    length=math.hypot(*key[:2]);nx,ny=key[0]/length,key[1]/length;b=key[2]/length
    point=(nx*b-ny*value,ny*b+nx*value)
    for face,start in rows:
        _,fx,fy,bound,cx,cy,tx,ty,lo,hi=face
        if abs(fx-nx)<1e-7 and abs(fy-ny)<1e-7 and abs(bound-b)<1e-7:
            tangent=tx*point[0]+ty*point[1]
            if lo-2*TOLERANCE<=tangent<=hi+2*TOLERANCE:
                tangent=min(hi,max(lo,tangent))
                return start+tangent-lo,(cx+tx*tangent,cy+ty*tangent)
    # A vertex can touch another cell without a positive-length facet on this
    # line. Omitting it would miss a hole closed by a corner-only contact.
    best=None
    for face,start in rows:
        _,_,_,_,cx,cy,tx,ty,lo,hi=face
        for value,coordinate in ((lo,start),(hi,start+hi-lo)):
            error=(cx+tx*value-point[0])**2+(cy+ty*value-point[1])**2
            if best is None or error<best[0]:best=(error,coordinate)
    if best is not None and best[0] <= (2*TOLERANCE)**2:return best[1],point
    return None


def connected_contact_arc(intervals,perimeter,tolerance=TOLERANCE):
    """True for one connected arc, including a wrap across the canonical seam."""
    if not intervals:return False
    merged=[]
    pieces=[]
    for lo,hi in intervals:
        if lo>hi+tolerance:pieces.extend(((lo,perimeter),(0.,hi)))
        else:pieces.append((min(lo,hi),max(lo,hi)))
    for lo,hi in sorted(pieces):
        if merged and lo<=merged[-1][1]+tolerance:merged[-1][1]=max(merged[-1][1],hi)
        else:merged.append([lo,hi])
    components=len(merged)
    if components>1 and merged[0][0]+perimeter-merged[-1][1]<=tolerance:components-=1
    return components==1


def junctions_from_contacts(contacts,perimeter,tolerance=TOLERANCE):
    """New local junction points and the existing rooms meeting at each one."""
    endpoints=[]
    for nid,lo,hi,p,q in contacts:
        endpoints.extend(((lo,nid,p),(hi,nid,q)))
    groups=[]
    for item in sorted(endpoints,key=lambda row:row[0]):
        if groups and item[0]-groups[-1][-1][0]<=tolerance:groups[-1].append(item)
        else:groups.append([item])
    if len(groups)>1 and groups[0][0][0]+perimeter-groups[-1][-1][0]<=tolerance:
        groups[0]=groups.pop()+groups[0]
    result=[]
    for group in groups:
        neighbors=frozenset(row[1] for row in group)
        if len(neighbors)>=2:
            point=(sum(row[2][0] for row in group)/len(group),sum(row[2][1] for row in group)/len(group))
            result.append((point,neighbors))
    return result
