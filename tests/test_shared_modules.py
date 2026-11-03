"""Independent correctness cases, not performance/quality benchmarks."""
import unittest
import math
from typed_cell import BuildingGraph, CellType, VerticalScope
from shared_modules import infer, validate, area, SizePrior
from voronoi_realizer import SE2MotifMatcher


class SharedModulesTest(unittest.TestCase):
    def test_rotation_not_reflection(self):
        matcher=SE2MotifMatcher(length_tolerance=1e-6,angle_tolerance_deg=.001)
        star=[(4,0),(0,5),(-6,2)]
        theta=.713
        from shared_modules import turn
        self.assertTrue(matcher.are_stars_congruent(star,[turn(p,theta) for p in star])[0])
        self.assertFalse(matcher.are_stars_congruent(star,[(x,-y) for x,y in star])[0])

    def test_budget_never_welds_incompatible_modules(self):
        from voronoi_realizer import VoronoiRealizer
        g=BuildingGraph(1)
        for root,x,d in [('a',0,4),('b',30,7)]:
            g.add_node(root,x,0);g.add_node(root+'n',x+d,0);g.add_edge(root,root+'n')
        labels=VoronoiRealizer().classify_nodes_by_star_motifs(g,0,dict_cap=1)
        self.assertNotEqual(labels['a'],labels['b'])

    def test_complementary_evidence_and_rotation(self):
        g=BuildingGraph(1)
        # Two incomplete occurrences have a common east contact and complementary north/south.
        for root,x,ys in [('a',0,[4]),('b',30,[-4])]:
            g.add_node(root,x,0)
            g.add_node(root+'e',x+4,0); g.add_edge(root,root+'e')
            for j,y in enumerate(ys):
                g.add_node(root+str(j),x,y);g.add_edge(root,root+str(j))
        r=infer(g)
        self.assertEqual(r.occurrences['a'].prototype,r.occurrences['b'].prototype)
        p=r.prototypes[r.occurrences['a'].prototype]
        self.assertGreater(len(p.constraints),2)

    def test_full_height_one_shape(self):
        g=BuildingGraph(2)
        g.add_node('stack',0,0,scope=VerticalScope.MULTI_FLOOR)
        g.add_node('a',4,0);g.add_edge('stack','a')
        g.add_node('b',0,6,floor_index=1);g.add_edge('stack_f01','b')
        r=infer(g)
        self.assertEqual(len(r.occurrences['stack'].nodes),2)
        from voronoi_realizer import VoronoiRealizer
        v=VoronoiRealizer()
        p0=next(p for p in v.realize_floor(g,0,[(-20,-20),(20,-20),(20,20),(-20,20)]) if p['node_id']=='stack')
        p1=next(p for p in v.realize_floor(g,1,[(-20,-20),(20,-20),(20,20),(-20,20)]) if p['node_id']=='stack_f01')
        self.assertEqual(p0['polygon'],p1['polygon'])

    def test_hole_has_no_access_area_or_fabrication_credit(self):
        g=BuildingGraph(1)
        g.add_node('core',0,0,cell_type=CellType.CORE)
        g.add_node('hole',4,0,cell_type=CellType.VOID)
        g.add_node('r',8,0)
        g.add_edge('core','hole');g.add_edge('hole','r')
        self.assertFalse(g.validate_circulation_connectivity())
        m=g.evaluate_graph_metrics(0)
        self.assertFalse(m['topologyValid'])
        self.assertEqual(m['reuseAudit']['independentOccurrences'],2)
        self.assertIsNone(m['sunExposure'])

    def test_atomic_core_move_and_rollback(self):
        g=BuildingGraph(2)
        g.add_node('old',0,0,cell_type=CellType.CORE,scope=VerticalScope.MULTI_FLOOR)
        g.add_node('new',4,0,scope=VerticalScope.MULTI_FLOOR)
        g.add_edge('old','new');g.add_edge('old_f01','new_f01')
        g.reassign_functions({'old':CellType.ROOM,'new':CellType.CORE})
        self.assertEqual(g.nodes['new_f01'].cell_type,CellType.CORE)
        with self.assertRaises(ValueError):g.reassign_functions({'new':CellType.VOID})
        self.assertEqual(g.nodes['new'].cell_type,CellType.CORE)

    def test_site_does_not_clip_prototype(self):
        g=BuildingGraph(1);g.add_node('a',0,0,cell_type=CellType.CORE)
        r=infer(g); original=list(r.polygon('a'))
        audit=validate(r,{0:[(-1,-1),(1,-1),(1,1),(-1,1)]})
        self.assertFalse(audit['valid']); self.assertEqual(original,r.polygon('a'))
        self.assertTrue(r.prototypes[r.occurrences['a'].prototype].prior_boundary)

    def test_degenerate_coincident_nodes_unresolved(self):
        g=BuildingGraph(1);g.add_node('a',0,0);g.add_node('b',0,0)
        self.assertEqual(len(infer(g).unresolved),2)

    def test_growing_connections_does_not_call_voronoi(self):
        g=BuildingGraph(1)
        g.compute_floor_voronoi_cells=lambda *a,**k: self.fail('Voronoi called')
        g.add_node('a',0,0);g.add_node('b',4,0)
        g.grow_node_connections('b','a')
        self.assertTrue(g.has_edge('a','b'))

if __name__=='__main__': unittest.main()

class EvidenceAndActionTests(unittest.TestCase):
    def test_sun_context_and_missing_directions(self):
        from graph_evidence import sun_access
        self.assertIsNone(sun_access((0,0),0,[],[])['value'])
        building={'polygon':[(2,-2),(3,-2),(3,2),(2,2)],'height':10}
        self.assertEqual(sun_access((0,0),0,[building],[(0,.2)])['value'],0.)
        self.assertEqual(sun_access((0,0),0,[building],[(math.pi,.2)])['value'],1.)

    def test_actions_no_detached_or_nonfinite_placement(self):
        from graph_actions import apply_action
        g=BuildingGraph(1);g.add_node('root',0,0,cell_type=CellType.CORE)
        with self.assertRaises(KeyError):apply_action(g,dict(kind='attach',id='a',anchor='missing',x=4,y=0))
        self.assertEqual(len(g.nodes),1)
        apply_action(g,dict(kind='attach',id='hole',anchor='root',x=4,y=0,function='void'))
        self.assertTrue(g.has_edge('root','hole'))
        with self.assertRaises(ValueError):apply_action(g,dict(kind='pose',id='hole',x=float('nan'),y=0))
        self.assertEqual(g.nodes['hole'].x,4.)

    def test_renumber_and_rotation_area_invariance(self):
        from shared_modules import turn
        values=[]
        for theta,prefix in [(0,'a'),(.31,'z')]:
            g=BuildingGraph(1)
            for i,p in enumerate([(0,0),(4,0),(0,5)]):
                x,y=turn(p,theta);g.add_node(prefix+str(i),x+20,y-13)
            g.add_edge(prefix+'0',prefix+'1');g.add_edge(prefix+'0',prefix+'2')
            r=infer(g)
            values.append(sorted(round(area(p.polygon),5) for p in r.prototypes.values()))
        self.assertEqual(values[0],values[1])

    def test_rotated_realization_has_no_overlaps(self):
        from shared_modules import turn
        from shapely.geometry import Polygon
        g=BuildingGraph(1)
        for root,ox,oy,angle in [('a',25,25,0),('b',75,75,.64577)]:
            g.add_node(root,ox,oy,cell_type=CellType.CORE)
            for j,p in enumerate([(6,0),(0,8),(-5,0),(0,-7)]):
                x,y=turn(p,angle);g.add_node(root+str(j),ox+x,oy+y);g.add_edge(root,root+str(j))
        r=infer(g)
        polygons=[Polygon(r.polygon(oid)) for oid,o in r.occurrences.items() if o.prototype]
        for i,p in enumerate(polygons):
            for q in polygons[i+1:]:self.assertLess(p.intersection(q).area,1e-6)
