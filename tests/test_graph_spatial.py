"""Exposure/role regressions; these hand fixtures are not throughput benchmarks."""
import math
import unittest
from unittest.mock import patch
from graph_dictionary import GraphDictionary,Instance,make_shape
from graph_spatial import evidence,access_distances
from shared_modules import SizePrior
from typed_cell import BuildingGraph,CellType,VerticalScope

SQUARE=((1.,0.,2.),(-1.,0.,2.),(0.,1.,2.),(0.,-1.,2.))

def scene(gap=8.,floors=4,angle=0.):
    g=BuildingGraph(floors);g.size_prior=SizePrior();g.spatial_settings={}
    g.add_node('starter',-4*math.cos(angle),-4*math.sin(angle),cell_type=CellType.CORE,scope=VerticalScope.MULTI_FLOOR)
    b=g.module_bank=GraphDictionary(g);shape=make_shape(SQUARE,frozenset(),g.size_prior)
    b.shapes={'module_1':shape};b.instances['starter'].angle=angle
    for oid,x,y,role in (('room',0,0,'room'),('north',0,4,'core'),('south',0,-4,'core'),('opposite',4+gap,0,'core')):
        x,y=x*math.cos(angle)-y*math.sin(angle),x*math.sin(angle)+y*math.cos(angle)
        g.add_node(oid,x,y,cell_type=CellType(role),scope=VerticalScope.MULTI_FLOOR)
        nodes=[n for n in g.nodes.values() if n.metadata.get('root_id',n.node_id)==oid]
        b.instances[oid]=Instance(oid,nodes,'module_1',angle);b.members['module_1'].add(oid)
        for n in nodes:b.floor_nodes[n.floor_index].append(n)
    return g,b

class SpatialTests(unittest.TestCase):
    def test_only_livable_rooms_have_daylight_obligations(self):
        g,b=scene();e=evidence(b);m=e.metrics(0)
        self.assertEqual(m['livableOccurrencesEvaluated'],1)
        self.assertAlmostEqual(m['livableAreaEvaluated'],16.)
        self.assertIsNone(e.occurrence('starter',0))
        g.reassign_functions({'room':CellType.CORE},require_access=False)
        m=e.metrics(0)
        self.assertIsNone(m['daylightAccessProxy']);self.assertEqual(m['daylightDeficit'],0.)
        self.assertFalse(m['spatialRequirementsMet']);self.assertEqual(m['residentialProgramDeficit'],1.)

    def test_core_obstructs_room_and_narrow_well_does_not_count_as_window(self):
        _,b=scene(gap=3.)
        row=evidence(b).occurrence('room',0)
        self.assertAlmostEqual(row['exposedLength'],4.,places=5)
        self.assertAlmostEqual(row['minimumFacingClearance'],3.,places=5)
        self.assertEqual(row['qualifiedFacadeLength'],0.)
        self.assertEqual(row['daylightAccessProxy'],0.)

    def test_height_and_floor_elevation_change_access(self):
        _,b=scene(gap=8.,floors=8);e=evidence(b)
        ground=e.occurrence('room',0);top=e.occurrence('room',7)
        self.assertLess(ground['daylightAccessProxy'],top['daylightAccessProxy'])
        _,low=scene(gap=8.,floors=1)
        self.assertAlmostEqual(evidence(low).occurrence('room',0)['daylightAccessProxy'],top['daylightAccessProxy'])

    def test_rotation_invariance_and_no_realization(self):
        _,a=scene(angle=0.);_,b=scene(angle=.713)
        with patch('shared_modules.infer',side_effect=AssertionError('realization forbidden')):
            for f in range(4):
                x=evidence(a).occurrence('room',f);y=evidence(b).occurrence('room',f)
                self.assertAlmostEqual(x['daylightAccessProxy'],y['daylightAccessProxy'])
                self.assertAlmostEqual(x['qualifiedFacadeLength'],y['qualifiedFacadeLength'])

    def test_cache_invalidates_for_remote_shared_type_change_and_role_change(self):
        g,b=scene();e=evidence(b);first=e.occurrence('room',0)
        self.assertIs(first,e.occurrence('room',0))
        b.shapes['module_1']=make_shape(((1.,0.,1.),(-1.,0.,1.),(0.,1.,1.),(0.,-1.,1.)),frozenset(),g.size_prior)
        second=e.occurrence('room',0)
        self.assertNotEqual(first['area'],second['area'])
        self.assertIsNot(first,second)

    def test_access_distance_uses_graph_paths_not_euclidean_shortcut(self):
        g=BuildingGraph(1)
        for i,(x,y,role) in enumerate(((0,0,'core'),(10,0,'room'),(10,10,'room'),(0,10,'room'))):
            g.add_node(str(i),x,y,cell_type=CellType(role))
            if i:g.add_edge(str(i-1),str(i))
        self.assertEqual(access_distances(g,0)['3'],30.)
        self.assertEqual(access_distances(g,0,extra_core='3')['2'],10.)

    def test_realized_ray_segment_oracle_agrees_on_known_well(self):
        from realized_spatial import RealizedSpatialEvidence
        for gap in (3.,8.,20.):
            _,b=scene(gap=gap,angle=.371)
            predicted=evidence(b)
            actual=RealizedSpatialEvidence(b.inference())
            for floor in (0,3):
                a=predicted.occurrence('room',floor);c=actual.occurrence('room',floor)
                self.assertAlmostEqual(a['daylightAccessProxy'],c['daylightAccessProxy'],places=6)
                self.assertAlmostEqual(a['qualifiedFacadeLength'],c['qualifiedFacadeLength'],places=6)

    def test_constraint_priority_prevents_fill_buying_bad_exposure(self):
        from graph_spatial import constrained_reward
        self.assertLess(constrained_reward(10000.,True,.1),constrained_reward(-10000.,True,0.))
        self.assertLess(constrained_reward(100.,True,.8),constrained_reward(0.,True,.2))
        self.assertEqual(constrained_reward(100.,False,0.),-1.)

    def test_overhanging_upper_room_is_an_obstruction_in_both_evaluators(self):
        from realized_spatial import RealizedSpatialEvidence
        g,b=scene(gap=20.,floors=4)
        g.add_node('overhang',2.,0.,floor_index=2,cell_type=CellType.CORE)
        b.instances['overhang']=Instance('overhang',[g.nodes['overhang']],'module_1',0.)
        b.members['module_1'].add('overhang')
        estimate=evidence(b).occurrence('room',0)
        actual=RealizedSpatialEvidence(b.inference()).occurrence('room',0)
        self.assertAlmostEqual(estimate['daylightAccessProxy'],actual['daylightAccessProxy'],places=6)
        self.assertLess(estimate['daylightAccessProxy'],1.)

    def test_function_choice_preserves_shared_shape_and_full_height(self):
        from dataclasses import replace
        g=BuildingGraph(3);g.size_prior=SizePrior()
        g.add_node('core',0.,0.,cell_type=CellType.CORE,scope=VerticalScope.MULTI_FLOOR)
        b=g.module_bank=GraphDictionary(g);b.shapes['module_1']=make_shape(SQUARE,frozenset(),g.size_prior)
        plan=b.probe(4.,0.,0,'multi_floor',preferred_pid='module_1',preferred_angle=0.)[0]
        b.commit(replace(plan,function='core'),'second')
        self.assertEqual(len(b.shapes),1)
        self.assertEqual(len({i.id for i in b.instances.values() if i.nodes[0].cell_type==CellType.CORE}),2)
        self.assertTrue(all(n.cell_type==CellType.CORE for n in b.instances['second'].nodes))
        before=b.shapes['module_1'];g.reassign_functions({'second':CellType.ROOM})
        self.assertIs(b.shapes['module_1'],before)
        self.assertTrue(all(n.cell_type==CellType.ROOM for n in b.instances['second'].nodes))

    def test_old_checkpoint_migrates_and_new_role_inputs_get_gradients(self):
        import copy,torch
        from graph_policy import GraphLearner
        g=BuildingGraph(1);g.add_node('core',0,0,cell_type=CellType.CORE)
        learner=GraphLearner(seed=12);state=copy.deepcopy(learner.state())
        state['schema']=3
        state['model']={k:v for k,v in state['model'].items() if not k.startswith('spatial.')}
        state['optimizer']['param_groups'][0]['params']=state['optimizer']['param_groups'][0]['params'][:-4]
        migrated=GraphLearner();migrated.load(state)
        for key,value in state['model'].items():self.assertTrue(torch.equal(value,migrated.model.state_dict()[key]))
        before=migrated.model.spatial[-1].weight.detach().clone()
        with patch('torch.rand',wraps=torch.rand):
            migrated.choose(g,[[0.]*18,[0.]*12+[1.,1.,1.,1.,1.,1.]],training=True)
            stats=migrated.finish(.5)
        self.assertEqual(stats['policyUpdateCount'],1)
        self.assertFalse(torch.equal(before,migrated.model.spatial[-1].weight))

    def test_submicrometre_seam_does_not_become_window_frontage(self):
        import numpy as np
        from graph_spatial import _ray_intervals
        planes=np.array(((1.,0.,2.),(-1.,0.,2.),(0.,1.,2.),(0.,-1.,2.)))
        entry,_=_ray_intervals(np.array([[2.+4e-7,0.]]),np.array([[1.,0.]]),planes)
        self.assertEqual(entry[0],0.)

    def test_spatial_event_is_strict_json_serializable(self):
        import json
        from realized_spatial import audit_spatial
        _,b=scene();data=audit_spatial(b.inference())
        json.dumps(data,allow_nan=False)

    def test_nearly_collinear_aliases_cannot_duplicate_window_frontage(self):
        from graph_spatial import _samples
        from shared_modules import _bounded_polygon
        planes=((-0.94021512,0.34058117,2.28704176),(-0.94021511,0.3405812,2.28704176),
            (-0.08488672,-0.99639061,2.45067958),(-0.08488668,-0.99639061,2.45067952),
            (-0.08488666,-0.99639061,2.45067956),(0.10226605,0.99475708,3.25410283),
            (0.1022661,0.99475708,3.25410278),(0.51085601,0.85966629,3.53146407),
            (0.51363517,-0.85800869,3.3038354),(0.51363519,-0.85800868,3.30383542),
            (1.,-1e-8,2.48616046),(1.,3e-8,2.48616047))
        prior=SizePrior();shape=make_shape(planes,frozenset(),prior)
        poly=_bounded_polygon(tuple(((x,y),b) for x,y,b in planes),(),prior)
        perimeter=sum(math.dist(a,b) for a,b in zip(poly,poly[1:]+poly[:1]))
        self.assertAlmostEqual(float(_samples(shape,1.)[:,4].sum()),perimeter,places=5)

if __name__=='__main__':unittest.main()

class ActiveEpisodeTimingTests(unittest.TestCase):
    def test_server_work_clock_excludes_idle_between_steps(self):
        import server
        t=server.ParallelTrainer();clock=[100.];durations=[]
        def fake_step(*_):
            clock[0]+=2.;t.step_number+=1
            durations.append(t._active_episode_duration())
            return {}
        t._step_impl=fake_step
        try:
            with patch('server.time.perf_counter',side_effect=lambda:clock[0]):
                t.step(t.generation_id,t.episode)
                clock[0]+=60.
                t.step(t.generation_id,t.episode)
                self.assertEqual(durations,[2.,4.])
                self.assertEqual(t._active_episode_duration(),4.)
        finally:t.executor.shutdown(wait=True)

class SpatialPreviewContractTests(unittest.TestCase):
    def test_pause_preview_exports_livable_metrics_without_training_or_inventing_success(self):
        import server,torch
        t=server.ParallelTrainer(dict(generatorEngine='graph_voronoi',siteAreaTier='L',boundaryType='rect',parallelEnvironments=1,maxModules=10,seed=123))
        try:
            t.update_settings({'seed':123});t.step(t.generation_id,t.episode)
            before={k:v.detach().clone() for k,v in t.graph_learner.model.state_dict().items()}
            event=t.evaluate(t.generation_id,t.episode)
            self.assertIn('daylightAccessProxy',event['metrics'])
            self.assertIn('spatialRequirementsMet',event['metrics'])
            self.assertIn('residentialSpatial',event['validation'])
            self.assertFalse(event['validation']['residentialSpatial']['environmentalComplianceVerified'])
            for k,v in before.items():self.assertTrue(torch.equal(v,t.graph_learner.model.state_dict()[k]))
        finally:t.executor.shutdown(wait=True)

class AntiThinningTests(unittest.TestCase):
    def test_tiny_occupied_patch_cannot_buy_feasibility_with_good_exposure(self):
        g,b=scene(gap=20.,floors=1)
        g.site_boundaries={0:[(-100.,-100.),(100.,-100.),(100.,100.),(-100.,100.)]}
        g.spatial_settings=dict(graphMinResidentialShare=.01,graphMinRoomExposure=.01,graphMaxAccessDistance=1000.)
        g.add_edge('room','starter')
        m=evidence(b).metrics(0)
        self.assertEqual(m['daylightDeficit'],0.)
        self.assertGreater(m['fillDeficit'],.99)
        self.assertFalse(m['spatialRequirementsMet'])
