"""Correctness/lifecycle checks, not throughput or convergence benchmarks."""
import copy
import math
import unittest
from unittest.mock import patch
import torch
from graph_proxy import GraphSketch, contact_length, refresh_local_contacts, star_signature
from typed_cell import BuildingGraph, CellType


class NumericContactTests(unittest.TestCase):
    def test_bisector_contact_and_occlusion(self):
        self.assertAlmostEqual(contact_length((0,0),(4,0),[],4.5),2*math.sqrt(4.5**2-4))
        self.assertEqual(contact_length((0,0),(4,0),[(2,0)],4.5),0.)
        self.assertEqual(contact_length((0,0),(10,0),[],4.5),0.)

    def test_new_point_removes_occluded_old_connection(self):
        g=BuildingGraph(1)
        g.add_node('a',0,0);g.add_node('b',6,0)
        refresh_local_contacts(g,['a','b'],4.5)
        self.assertTrue(g.has_edge('a','b'))
        g.add_node('c',3,0);refresh_local_contacts(g,['c'],4.5)
        self.assertFalse(g.has_edge('a','b'))
        self.assertTrue(g.has_edge('a','c'));self.assertTrue(g.has_edge('b','c'))

    def test_rotation_only_provisional_signature(self):
        arms=[(4,0),(0,5),(-6,2)]
        c,s=math.cos(.713),math.sin(.713)
        self.assertEqual(star_signature(arms),star_signature([(c*x-s*y,s*x+c*y) for x,y in arms]))
        self.assertNotEqual(star_signature(arms),star_signature([(x,-y) for x,y in arms]))

    def test_provisional_labels_do_not_earn_confirmed_reuse(self):
        g=BuildingGraph(1)
        g.add_node('core',0,0,cell_type=CellType.CORE)
        g.add_node('r',6,0);g.add_edge('core','r')
        g.add_node('void',12,0,cell_type=CellType.VOID);g.add_edge('r','void')
        m=GraphSketch(g).metrics(0)
        self.assertEqual(m['reuseRatio'],0.)
        self.assertEqual(m['reuseAudit']['independentOccurrences'],2)
        self.assertEqual(m['moduleIdentityStatus'],'provisional')
        self.assertGreater(m['filledArea'],0.)

    def test_area_estimate_is_intrinsic_and_insertion_invariant(self):
        from graph_proxy import radial_area
        v=[(4,0),(0,5),(-6,2)]
        angle=.713;c,s=math.cos(angle),math.sin(angle)
        rotated=[(c*x-s*y,s*x+c*y) for x,y in reversed(v)]
        self.assertAlmostEqual(radial_area(v,4.5),radial_area(rotated,4.5),places=8)

    def test_static_hole_and_site_clearance_are_graph_constraints(self):
        from graph_proxy import origin_fits
        site=[(-20,-20),(20,-20),(20,20),(-20,20)]
        hole=[(-2,-2),(2,-2),(2,2),(-2,2)]
        self.assertFalse(origin_fits((0,0),site,[hole]))
        self.assertTrue(origin_fits((10,0),site,[hole]))
        self.assertFalse(origin_fits((19,0),site))


class GraphOnlyLifecycleTests(unittest.TestCase):
    def trainer(self):
        from server import ParallelTrainer
        t=ParallelTrainer(dict(generatorEngine='graph_voronoi',graphController='neural',
            boundaryType='rect',siteAreaTier='L',parallelEnvironments=4,maxModules=120,seed=123))
        t.new_site();self.addCleanup(t.executor.shutdown,wait=True)
        return t

    def test_growth_never_realizes_or_copies_graph(self):
        t=self.trainer()
        with patch('shared_modules.infer',side_effect=AssertionError('inference in growth')), \
             patch('shared_modules._bounded_polygon',side_effect=AssertionError('polygon in growth')), \
             patch('shapely.geometry.Polygon',side_effect=AssertionError('GEOS in growth')), \
             patch('copy.deepcopy',side_effect=AssertionError('deep copy in growth')):
            for _ in range(4):
                e=t.step(t.generation_id,t.episode)
                self.assertEqual(e['type'],'placements')
                self.assertFalse(e['graphState']['realized'])
                self.assertEqual(e['placements'],[])
                self.assertTrue(all(not p['poly'] for p in e['dictionary']))
        self.assertEqual(t.graph_learner.updates,0)

    def test_pause_solves_once_preserves_training_then_resumes_graph(self):
        import shared_modules
        t=self.trainer();t.step(t.generation_id,t.episode)
        before=copy.deepcopy(t.graph_learner.state());count=len(t.graph_learner.trajectory)
        with patch('shared_modules.infer',wraps=shared_modules.infer) as solve:
            e=t.evaluate(t.generation_id,t.episode)
        self.assertEqual(solve.call_count,1)
        self.assertTrue(e['graphState']['realized'])
        self.assertFalse(e['graphState']['isComplete'])
        self.assertTrue(e['placements'])
        self.assertEqual(len(t.graph_learner.trajectory),count)
        for k,v in t.graph_learner.model.state_dict().items():
            self.assertTrue(torch.equal(v,before['model'][k]))
        self.assertEqual(t.graph_learner.updates,0)
        with patch('shared_modules.infer',side_effect=AssertionError('inference after resume')):
            resumed=t.step(t.generation_id,t.episode)
        self.assertFalse(resumed['graphState']['realized'])
        self.assertEqual(resumed['placements'],[])

    def test_entire_training_episode_never_realizes_and_preview_is_separate(self):
        import shared_modules
        t=self.trainer()
        # Small cap is a lifecycle fixture, not a performance benchmark.
        t.settings['maxModules']=10
        with patch('shared_modules.infer',side_effect=AssertionError('training realized geometry')), \
             patch('shared_modules.validate',side_effect=AssertionError('training used geometry oracle')), \
             patch('shared_modules._bounded_polygon',side_effect=AssertionError('training constructed polygons')):
            for _ in range(20):
                e=t.step(t.generation_id,t.episode)
                if e['type']=='episodeDone':break
            else:self.fail('episode did not complete')
        self.assertEqual(e['validation']['status'],'not_run')
        self.assertIsNone(e['metrics']['geometryValid'])
        self.assertFalse(e['graphState']['realized'])
        self.assertEqual(t.graph_learner.updates,1)
        self.assertGreater(e['metrics']['gradientNorm'],0.)
        before=copy.deepcopy(t.graph_learner.state())
        with patch('shared_modules.infer',wraps=shared_modules.infer) as solve:
            preview=t.evaluate(t.generation_id,t.episode)
        self.assertEqual(solve.call_count,1)
        self.assertTrue(preview['graphState']['isComplete'])
        self.assertTrue(preview['graphState']['realized'])
        self.assertTrue(preview['validation']['valid'])
        self.assertAlmostEqual(float(e['metrics']['score']),preview['metrics']['score'],delta=.01)
        self.assertAlmostEqual(e['metrics']['reuseBonus'],preview['metrics']['reuseBonus'],places=6)
        self.assertEqual(t.graph_learner.updates,1)
        self.assertIsNone(t.building_graph)
        for k,v in t.graph_learner.model.state_dict().items():self.assertTrue(torch.equal(v,before['model'][k]))

    def test_full_height_contacts_use_all_floors_without_polygons(self):
        from typed_cell import VerticalScope
        g=BuildingGraph(2)
        g.add_node('stack',0,0,scope=VerticalScope.MULTI_FLOOR)
        g.add_node('east',6,0);g.add_node('north',0,6,floor_index=1)
        refresh_local_contacts(g,['stack','east','north'],4.5)
        self.assertTrue(g.has_edge('stack','east'))
        g.add_node('occluder',2,0,floor_index=1)
        refresh_local_contacts(g,['occluder'],4.5)
        self.assertFalse(g.has_edge('stack','east')) # evidence on floor 1 changes the shared footprint on floor 0

class BoundedBatchTests(unittest.TestCase):
    def test_training_batch_is_bounded_and_inference_remains_one_step(self):
        from server import ParallelTrainer
        t=ParallelTrainer(dict(generatorEngine='graph_voronoi',boundaryType='rect',siteAreaTier='L',
            parallelEnvironments=4,maxModules=10))
        try:
            t.new_site();e=t.step_batch(t.generation_id,t.episode,window_ms=1000)
            self.assertGreater(e['batchSteps'],1)
            self.assertLessEqual(e['batchSteps'],16)
            self.assertLessEqual(len(e['dictionary']),15)
            t.new_site();t.set_mode('inference');e=t.step_batch(t.generation_id,t.episode)
            self.assertNotIn('batchSteps',e)
            self.assertEqual(t.step_number,1)
        finally:t.executor.shutdown(wait=True)

    def test_restricted_dictionary_setting_remains_editable(self):
        from server import DEFAULT_SETTINGS,validate_settings_patch,SettingsError
        settings=validate_settings_patch(DEFAULT_SETTINGS,dict(generatorEngine='graph_voronoi',graphMaxTypes=1))
        self.assertEqual(settings['dictCap'],1)
        changed=validate_settings_patch(settings,dict(learningRate=.002))
        self.assertEqual(changed['dictCap'],1)
        with self.assertRaises(SettingsError):
            validate_settings_patch(DEFAULT_SETTINGS,dict(graphMaxTypes=600))
