"""Independent completed-layout gap diagnostics, never a graph training reward.

Topology cleanup below is diagnostic only. It never changes output footprints,
overlap tests, containment tests, areas credited to modules, or shared prototypes.
"""
import time


def polygon_parts(geometry):
    if geometry.is_empty:return []
    if geometry.geom_type=='Polygon':return [geometry]
    return [part for child in getattr(geometry,'geoms',()) for part in polygon_parts(child)]


def audit_floor_gaps(site,built,planned_voids=(),union=None,min_report_area=.01,seam_tolerance=1e-6,narrow_radius=.5):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union,polylabel
    start=time.perf_counter()
    union=unary_union(built) if union is None else union
    planned=unary_union(list(planned_voids))
    # Close floating-point seams for detecting enclosed regions, not for passing
    # geometric validity or claiming added floor area. A real narrow slit also
    # should not make a large unintended interior gap disappear from this audit.
    diagnostic=union.buffer(seam_tolerance,join_style=2).buffer(-seam_tolerance,join_style=2)
    raw_holes=[Polygon(ring) for part in polygon_parts(diagnostic) for ring in part.interiors]
    unplanned=unary_union(raw_holes).intersection(site).difference(planned)
    parts=polygon_parts(unplanned)
    holes=[p for p in parts if p.area>min_report_area]
    records=[]
    for hole in holes:
        label=polylabel(hole,tolerance=.025)
        records.append(dict(area=hole.area,perimeter=hole.length,
            approximateLargestInscribedDiameter=2*label.distance(hole.boundary),
            poly=[dict(x=x,y=y) for x,y in list(hole.exterior.coords)[:-1]]))
    # A morphological diagnostic for narrow EXTERIOR crevices. It also responds
    # to some benign concave corners: it is reported separately, not a hard
    # architectural validity test or a calibrated minimum-width estimator.
    closed=diagnostic.buffer(narrow_radius,join_style=2).buffer(-narrow_radius,join_style=2)
    crevices=closed.difference(diagnostic).intersection(site).difference(planned).difference(unplanned)
    return dict(noUnplannedEnclosedGaps=not records,unplannedEnclosedGapCount=len(records),
        rawUnplannedEnclosedGapArea=sum(p.area for p in parts),
        largestRawUnplannedEnclosedGapArea=max((p.area for p in parts),default=0.),
        unplannedEnclosedGapArea=sum(r['area'] for r in records),
        largestUnplannedEnclosedGapArea=max((r['area'] for r in records),default=0.),gaps=records,
        narrowExteriorCreviceAreaDiagnostic=crevices.area,narrowDiagnosticRadius=narrow_radius,
        minimumReportedArea=min_report_area,seamTolerance=seam_tolerance,seconds=time.perf_counter()-start,
        changesFootprints=False,doorOrCourtyardDesignVerified=False)


def audit_solution_gaps(solution):
    from shapely.geometry import Polygon
    rows={}
    for f,boundary in solution.graph.site_boundaries.items():
        xy=lambda p:[(v['x'],v['y']) if isinstance(v,dict) else v for v in p]
        site=Polygon(xy(boundary),[xy(h) for h in solution.graph.site_holes.get(f,())])
        built=[];voids=[]
        for oid,o in solution.occurrences.items():
            if not o.prototype:continue
            polygon=Polygon(solution.polygon(oid))
            for node in o.nodes:
                if node.floor_index==f:(voids if node.cell_type.value=='void' else built).append(polygon)
        rows[f]=audit_floor_gaps(site,built,voids)
    return dict(noUnplannedEnclosedGaps=all(r['noUnplannedEnclosedGaps'] for r in rows.values()),
        unplannedEnclosedGapArea=sum(r['unplannedEnclosedGapArea'] for r in rows.values()),perFloor=rows,
        seconds=sum(r['seconds'] for r in rows.values()))
