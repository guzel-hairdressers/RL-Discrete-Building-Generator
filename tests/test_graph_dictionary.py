"""Correctness checks for implicit shared types; these are not speed benchmarks."""
import math
import unittest
from typed_cell import BuildingGraph,CellType,VerticalScope
from shared_modules import SizePrior,area,_bounded_polygon,turn,validate
from graph_dictionary import GraphDictionary,make_shape,plane_key

class ImplicitShapeTests(unittest.TestCase):
    def test_scalar_area_matches_polygon_adapter_on_oblique_constraints(self):
        import random
        rng=random.Random(135)
        prior=SizePrior()
        for _ in range(80):
            planes=tuple(sorted({plane_key((math.cos(a),math.sin(a),b))
                for a,b in [(rng.uniform(-math.pi,math.pi),rng.uniform(1.3,4.4)) for i in range(7)]}))
            shape=make_shape(planes,frozenset(),prior)
            if shape is None:continue
            polygon=_bounded_polygon(tuple(((x,y),b) for x,y,b in shape.planes),(),prior)
            self.assertIsNotNone(polygon)
            self.assertAlmostEqual(shape.area,area(polygon),places=5)

    def test_an_added_cut_cannot_erase_a_required_contact(self):
        prior=SizePrior();p=(1.,0.,2.)
        self.assertIsNotNone(make_shape((p,),frozenset({p}),prior))
        self.assertIsNone(make_shape((p,(1.,0.,1.)),frozenset({p}),prior))

    def test_near_parallel_evidence_cannot_expand_a_module_when_pruned(self):
        planes=((-0.95218295,-0.30552845,2.70223018),(-0.66449152,-0.74729581,2.80408245),
            (-0.48787101,0.87291573,1.45474621),(-0.48787101,0.87291574,1.45474621),
            (0.48787101,-0.87291574,1.45474621),(1.,0.,2.02593477),(0.71966069,0.69432593,1.82892617))
        prior=SizePrior();shape=make_shape(tuple(sorted(planes)),frozenset(),prior)
        self.assertIsNotNone(shape)
        polygon=_bounded_polygon(tuple(((x,y),b) for x,y,b in shape.planes),(),prior)
        for nx,ny,b in planes:
            self.assertLessEqual(max(nx*x+ny*y-b for x,y in polygon),1e-6)
        self.assertAlmostEqual(shape.area,area(polygon),places=5)

    def test_parallel_duplicate_observations_count_one_facet_and_keep_contact_aliases(self):
        prior=SizePrior();planes=((1.,0.,2.),(1.,0.,2.+1e-8),(1.,0.,2.+2e-8))
        shape=make_shape(planes,frozenset(planes),prior)
        polygon=_bounded_polygon(tuple(((x,y),b) for x,y,b in planes),(),prior)
        self.assertIsNotNone(shape)
        self.assertAlmostEqual(shape.area,area(polygon),places=5)
        self.assertEqual(len(shape.planes),1)
        for p in planes:self.assertAlmostEqual(shape.interval(p)[1]-shape.interval(p)[0],shape.interval(planes[0])[1]-shape.interval(planes[0])[0])

    def test_contact_alias_tolerance_cannot_bridge_a_millimetre_difference(self):
        planes=((1.,0.,2.),(1.,0.,2.001))
        self.assertIsNone(make_shape(planes,frozenset(planes),SizePrior()))

    def test_incremental_active_prior_pruning_matches_full_adapter(self):
        from graph_dictionary import shape_with
        prior=SizePrior();shape=make_shape((),frozenset(),prior)
        evidence=[]
        for i in range(11):
            a=.23+i*2*math.pi/7;plane=plane_key((math.cos(a),math.sin(a),2.+.2*math.sin(i)))
            evidence.append(plane);shape=shape_with(shape,(plane,),(),prior)
            self.assertIsNotNone(shape)
            polygon=_bounded_polygon(tuple(((x,y),b) for x,y,b in evidence),(),prior)
            self.assertAlmostEqual(shape.area,area(polygon),places=5)
        self.assertEqual(len(shape.prior_planes),0)

class SharedDictionaryTests(unittest.TestCase):
    def graph(self,cap=2,floors=1):
        g=BuildingGraph(floors);g.size_prior=SizePrior()
        g.add_node('core',0,0,cell_type=CellType.CORE,scope=VerticalScope.MULTI_FLOOR)
        g.module_bank=GraphDictionary(g,cap)
        return g,g.module_bank

    def test_same_shape_reused_under_rotation_without_a_new_type(self):
        g,bank=self.graph(1)
        plans=bank.probe(4,0,0,'independent')
        self.assertEqual(len(plans),1)
        bank.commit(plans[0],'a')
        self.assertEqual(len(bank.shapes),1)
        self.assertEqual(g.nodes['core'].module_id,g.nodes['a'].module_id)
        result=bank.inference()
        self.assertEqual(result.reuse()['confirmedReuseRatio'],1.)
        audit=validate(result,{0:[(-20,-20),(20,-20),(20,20),(-20,20)]})
        self.assertTrue(audit['valid'],audit['violations'])

    def test_budget_never_forces_incompatible_connections_into_one_type(self):
        g,bank=self.graph(1)
        bank.commit(bank.probe(4,0,0,'independent')[0],'a')
        before=dict(bank.shapes)
        # No 5m contact can be assigned to the module's existing 4m facet.
        self.assertEqual(bank.probe(-5,0,0,'independent'),[])
        self.assertEqual(before,bank.shapes)
        self.assertEqual(len(bank.shapes),1)

    def test_full_height_scope_has_one_prototype_and_one_area(self):
        g,bank=self.graph(2,3)
        plans=bank.probe(4,0,0,'multi_floor');self.assertTrue(plans)
        bank.commit(plans[0],'stack')
        nodes=[n for n in g.nodes.values() if n.node_id=='stack' or n.metadata.get('root_id')=='stack']
        self.assertEqual(len(nodes),3)
        self.assertEqual(len({n.module_id for n in nodes}),1)
        self.assertEqual(len({n.area for n in nodes}),1)
        self.assertTrue(g.validate_circulation_connectivity())

    def test_probe_does_not_realize_any_polygons(self):
        from unittest.mock import patch
        g,bank=self.graph(2)
        with patch('shared_modules._bounded_polygon',side_effect=AssertionError('polygon during graph growth')):
            plans=bank.probe(4,0,0,'independent');bank.commit(plans[0],'a')
        self.assertLessEqual(len(bank.shapes),2)

class IndependentReuseRewardTests(unittest.TestCase):
    graph=SharedDictionaryTests.graph
    def test_vertical_copies_earn_no_reuse_bonus(self):
        from graph_proxy import GraphSketch
        g,bank=self.graph(1,8)
        metrics=GraphSketch(g).metrics(0)
        self.assertEqual(metrics['reuseBonus'],0.)
        self.assertEqual(metrics['reuseAudit']['independentOccurrences'],1)
        bank.commit(bank.probe(4,0,0,'multi_floor')[0],'stack')
        metrics=GraphSketch(g).metrics(0)
        self.assertEqual(metrics['reuseAudit']['independentOccurrences'],2)
        self.assertEqual(metrics['reuseBonus'],10.)

    def test_holes_earn_no_fabrication_reuse_bonus(self):
        from graph_proxy import GraphSketch
        g,bank=self.graph(1)
        bank.commit(bank.probe(4,0,0,'independent')[0],'hole')
        g.nodes['hole'].cell_type=CellType.VOID
        metrics=GraphSketch(g).metrics(0)
        self.assertEqual(metrics['reuseBonus'],0.)
        self.assertEqual(metrics['reuseAudit']['independentOccurrences'],1)

    def test_realization_reports_the_same_independent_reuse_reward(self):
        from graph_proxy import GraphSketch
        g,bank=self.graph(1)
        bank.commit(bank.probe(4,0,0,'independent')[0],'room')
        result=bank.inference()
        audit=validate(result,{0:[(-20,-20),(20,-20),(20,20),(-20,20)]})
        before=GraphSketch(g).metrics(0)
        after=g.evaluate_graph_metrics(0,site_area=1000.,realization=(result,audit))
        self.assertEqual(before['reuseBonus'],after['reuseBonus'])
        self.assertAlmostEqual(before['score'],after['score'],places=5)
