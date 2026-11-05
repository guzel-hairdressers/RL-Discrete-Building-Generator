"""Continuity regressions, not speed benchmarks or generator shape presets."""
import math
import unittest
from unittest.mock import patch

from graph_continuity import connected_contact_arc,boundary_interval
from graph_dictionary import GraphDictionary,make_shape
from shared_modules import SizePrior,validate
from typed_cell import BuildingGraph,CellType,VerticalScope

SQUARE=((1.,0.,2.),(-1.,0.,2.),(0.,1.,2.),(0.,-1.,2.))
SITE=[(-30,-30),(30,-30),(30,30),(-30,30)]


def fixture(start=(-4,-4),enabled=True,floors=1):
    g=BuildingGraph(floors);g.size_prior=SizePrior();g.allow_unplanned_gaps=not enabled
    g.add_node('core',*start,cell_type=CellType.CORE,scope=VerticalScope.MULTI_FLOOR)
    g.module_bank=GraphDictionary(g);g.module_bank.shapes['module_1']=make_shape(SQUARE,frozenset(),g.size_prior)
    return g,g.module_bank


class ContinuityTests(unittest.TestCase):
    def test_circular_arc_seam_and_point_contacts(self):
        self.assertTrue(connected_contact_arc([(9.,1.)],10.))
        self.assertTrue(connected_contact_arc([(0.,1.),(9.,10.)],10.))
        self.assertTrue(connected_contact_arc([(1.,3.),(3.,3.)],10.))
        self.assertFalse(connected_contact_arc([(1.,3.),(4.,4.)],10.))
        self.assertFalse(connected_contact_arc([(1.,3.),(8.,9.)],10.))

    def test_growth_cannot_close_an_unplanned_ring(self):
        sequence=[(0,-4),(4,-4),(4,0),(4,4),(0,4),(-4,4),(-4,0)]
        for enabled in (False,True):
            g,b=fixture(enabled=enabled)
            for i,position in enumerate(sequence):
                plans=b.probe(*position,0,'independent',preferred_pid='module_1',preferred_angle=0.)
                if i<6 or not enabled:self.assertTrue(plans,(enabled,i,dict(b.rejections)))
                else:self.assertFalse(plans)
                if plans:b.commit(plans[0],f'n{i}')
            result=validate(b.inference(),{0:SITE})
            self.assertEqual(result['spatialQuality']['noUnplannedEnclosedGaps'],enabled)
            if not enabled:self.assertAlmostEqual(result['spatialQuality']['unplannedEnclosedGapArea'],16.,places=4)

    def test_shared_cut_must_preserve_junction_at_other_occurrence(self):
        for enabled in (False,True):
            g,b=fixture((-2,-2),enabled)
            for i,position in enumerate(((2,-2),(-2,2))):
                b.commit(b.probe(*position,0,'independent',preferred_pid='module_1',preferred_angle=0.)[0],f'n{i}')
            plans=b.probe(5.4,0.,0,'independent')
            if enabled:
                self.assertFalse(plans);self.assertGreater(b.rejections['junction_displaced'],0)
            else:
                self.assertTrue(plans);b.commit(plans[0],'cut')
                self.assertGreater(validate(b.inference(),{0:SITE})['spatialQuality']['unplannedEnclosedGapArea'],.6)

    def test_point_contact_is_retained_and_four_room_junction_can_close(self):
        g,b=fixture((-2,-2),floors=3)
        for i,position in enumerate(((2,-2),(-2,2),(2,2))):
            plans=b.probe(*position,0,'multi_floor',preferred_pid='module_1',preferred_angle=0.)
            self.assertTrue(plans);b.commit(plans[0],f'n{i}')
        self.assertTrue(b.junctions['core'])
        audit=validate(b.inference(),{f:SITE for f in range(3)})
        self.assertTrue(audit['valid']);self.assertTrue(audit['spatialQuality']['noUnplannedEnclosedGaps'])
        self.assertEqual(len(b.shapes),1)
        self.assertEqual(len({n.area for n in g.nodes.values()}),1)

    def test_explicit_courtyard_is_preserved_without_occupied_or_access_credit(self):
        g,b=fixture((0,-4))
        b.commit(b.probe(0,0,0,'independent',preferred_pid='module_1',preferred_angle=0.)[0],'courtyard')
        g.nodes['courtyard'].cell_type=CellType.VOID
        positions=((-4,-4),(-4,0),(-4,4),(0,4),(4,4),(4,0),(4,-4))
        for i,position in enumerate(positions):
            plans=b.probe(*position,0,'independent',preferred_pid='module_1',preferred_angle=0.)
            self.assertTrue(plans,(i,dict(b.rejections)));b.commit(plans[0],f'n{i}')
        audit=validate(b.inference(),{0:SITE})
        self.assertTrue(audit['valid']);self.assertTrue(audit['spatialQuality']['noUnplannedEnclosedGaps'])
        self.assertAlmostEqual(audit['perFloor'][0]['filledArea'],8*16.)

    def test_collinear_fragments_supply_the_whole_contact(self):
        planes=((-0.92849507,0.37134471,3.91795088),(-0.77627829,-0.63039037,2.23381998),
            (-0.77627829,-0.63039036,2.23381997),(-0.07914561,0.99686307,2.82521969),
            (0.07914561,-0.99686307,2.8252197),(0.77627829,0.63039036,2.23381997),(1.,0.,3.69173565))
        shape=make_shape(planes,frozenset(),SizePrior());key=(-.77627829,-.63039036,2.23381997)
        self.assertGreater(shape.interval(key)[1],1.8)
        self.assertGreater(boundary_interval(shape,key)[1],1.8)

    def test_certificates_do_not_realize_and_stale_plans_cannot_overwrite_them(self):
        g,b=fixture((-2,-2))
        with patch('shared_modules._bounded_polygon',side_effect=AssertionError('realization during growth')):
            a=b.probe(2,-2,0,'independent')[0];stale=b.probe(-2,2,0,'independent')[0]
            b.commit(a,'a')
            with self.assertRaisesRegex(ValueError,'stale'):b.commit(stale,'b')

    def test_oblique_growth_under_rigid_rotations_keeps_true_shared_shapes(self):
        for rotation in (0.,.371,1.813):
            g=BuildingGraph(2);g.size_prior=SizePrior()
            g.add_node('core',0,0,cell_type=CellType.CORE,scope=VerticalScope.MULTI_FLOOR)
            b=GraphDictionary(g);g.module_bank=b
            for i,(x,y) in enumerate(((4,0),(2,math.sqrt(12)),(6,math.sqrt(12)),(4,math.sqrt(48)))):
                c,s=math.cos(rotation),math.sin(rotation)
                plans=b.probe(c*x-s*y,s*x+c*y,0,'multi_floor')
                self.assertTrue(plans)
                b.commit(max(plans,key=lambda p:p.filled),f'n{i}')
            result=validate(b.inference(),{f:SITE for f in range(2)})
            self.assertTrue(result['valid']);self.assertTrue(result['spatialQuality']['noUnplannedEnclosedGaps'])
            old={oid:dict(points)for oid,points in b.junctions.items()}
            self.assertTrue(b.rebuild_continuity())
            self.assertTrue(b.junctions)

    def test_replay_cannot_certify_a_preexisting_hole(self):
        g,b=fixture(enabled=False)
        for i,position in enumerate(((0,-4),(4,-4),(4,0),(4,4),(0,4),(-4,4),(-4,0))):
            b.commit(b.probe(*position,0,'independent',preferred_pid='module_1',preferred_angle=0.)[0],f'n{i}')
        self.assertFalse(b.rebuild_continuity())

    def test_pooled_extremes_match_all_occurrence_witness_checks(self):
        from graph_continuity import point_inside
        from graph_dictionary import shape_with,plane_key
        import random
        g,b=fixture((-2,-2))
        for i,p in enumerate(((2,-2),(-2,2),(2,2))):
            b.commit(b.probe(*p,0,'independent',preferred_pid='module_1',preferred_angle=0.)[0],f'n{i}')
        rng=random.Random(433)
        for _ in range(100):
            angle=rng.uniform(-math.pi,math.pi);bound=rng.uniform(.2,3.)
            shape=shape_with(b.shapes['module_1'],[plane_key((math.cos(angle),math.sin(angle),bound))],(),g.size_prior)
            if shape is None:continue
            exhaustive=all(point_inside(shape,p) for oid in b.members['module_1'] for p in b.junctions.get(oid,{}).values())
            self.assertEqual(b._preserves_junctions({'module_1':shape}),exhaustive)
