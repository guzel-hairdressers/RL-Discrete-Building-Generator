import math
import unittest
from graph_dictionary import rotate
from realizer_experiments import corner_metrics,orthogonal_completion,public_circulation,realize_ports,wall_evidence
from shared_modules import Inference,Occurrence,Prototype,SizePrior,infer,validate
from typed_cell import BuildingGraph,CellType,VerticalScope


def corridor_case(angle=0.,floors=1):
    """Several rooms use the same long wall at non-bisector origin positions.

    This is a capability/correctness fixture, never a generation benchmark.
    """
    g=BuildingGraph(floors)
    g.site_boundaries={f:[rotate(p,angle) for p in [(-3,-3),(15,-3),(15,8),(-3,8)]] for f in range(floors)}
    g.site_holes={f:[] for f in range(floors)}
    shapes={'core':[(-1,-1),(1,-1),(1,1),(-1,1)],
        'corridor':[(-1,-1),(11,-1),(11,1),(-1,1)],
        'room':[(-1,-1),(1,-1),(1.6,2),(-1,2)]}
    entries=[('core',0.,0.,'core'),('corridor',2.,0.,'room')]
    entries.extend((f'room_{i}',2.+2*i,2.,'room') for i in range(6))
    occurrences={}
    for oid,x,y,role in entries:
        pid='room' if oid.startswith('room_') else oid
        x,y=rotate((x,y),angle)
        g.add_node(oid,x,y,cell_type=CellType(role),scope=VerticalScope.MULTI_FLOOR)
        nodes=[n for n in g.nodes.values() if n.node_id==oid or n.metadata.get('root_id')==oid]
        for n in nodes:n.orientation=angle;n.module_id=pid
        occurrences[oid]=Occurrence(oid,nodes,angle,pid)
    for f in range(floors):
        nid=lambda oid:oid if f==0 else f'{oid}_f{f:02d}'
        g.add_edge(nid('core'),nid('corridor'))
        for i in range(6):g.add_edge(nid('corridor'),nid(f'room_{i}'))
    # Oblique rooms overlap with each other if their outward slant is too large;
    # use one repeated sheared parallelogram rather than overlapping trapezoids.
    shapes['room']=[(-1,-1),(1,-1),(1.6,2),(-.4,2)]
    evidence=[dict(prototype=pid,normal=n,offset=b) for pid,p in shapes.items() for n,b in wall_evidence(p)]
    solution=realize_ports(g,occurrences,evidence,SizePrior(radius=12,max_area=500))
    for o in occurrences.values():
        from shared_modules import area
        for n in o.nodes:n.area=area(solution.prototypes[o.prototype].polygon)
    return solution


class RealizerTests(unittest.TestCase):
    def test_ports_support_multiple_rooms_on_one_corridor_wall_under_rotation(self):
        for angle in (0.,.613):
            solution=corridor_case(angle,2)
            audit=validate(solution,solution.graph.site_boundaries)
            self.assertTrue(audit['valid'],audit)
            midpoint=infer(solution.graph,solution.prior)
            # The same required long corridor contacts cannot all be represented
            # as ordinary midpoint bisectors of these stable origins.
            mid_audit=validate(midpoint,solution.graph.site_boundaries)
            self.assertFalse(mid_audit['valid'])

    def test_public_access_uses_corridor_not_private_room_traversal(self):
        solution=corridor_case(.3,2)
        report=public_circulation(solution,.5)
        self.assertTrue(report['valid'],report)
        self.assertEqual(report['perFloor'][0]['corridorOccurrences'],1)
        self.assertEqual(report['perFloor'][1]['corridorOccurrences'],1)
        self.assertEqual(report['perFloor'][0]['unitCount'],6)

    def test_corner_metrics_ignore_collinear_vertices_and_global_rotation(self):
        poly=[(-1,-1),(0,-1),(2,-1),(2,1),(-1,1)]
        a=corner_metrics(poly);b=corner_metrics([rotate(p,.43) for p in poly])
        self.assertEqual(a['corners'],4);self.assertAlmostEqual(a['weightedRightFraction'],1.)
        self.assertAlmostEqual(a['weightedDeviationDegrees'],b['weightedDeviationDegrees'],places=6)

    def test_incomplete_ports_keep_prior_boundaries_explicit(self):
        solution=corridor_case()
        incomplete=[dict(prototype=pid,normal=(1.,0.),offset=2.) for pid in solution.prototypes]
        result=realize_ports(solution.graph,solution.occurrences,incomplete,solution.prior)
        self.assertTrue(all(p.prior_boundary for p in result.prototypes.values()))

    def test_orthogonal_realizer_preserves_shared_contacts_and_origins(self):
        solution=corridor_case(.23,2);origins={oid:o.origin for oid,o in solution.occurrences.items()}
        changed,report=orthogonal_completion(solution,.02)
        self.assertEqual(origins,{oid:o.origin for oid,o in changed.occurrences.items()})
        self.assertTrue(validate(changed,solution.graph.site_boundaries)['valid'])
        self.assertGreater(report['candidates'],0)
