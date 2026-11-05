"""Research ablation correctness, not performance measurements."""
import copy
import math
import unittest
from unittest.mock import patch

import torch

from graph_dictionary import GraphDictionary, make_shape
from graph_experiments import (GraphExperiment, ResearchLearner, boundary_features,
    rebuild_after_pose, shape_inside_site)
from shared_modules import SizePrior, validate
from typed_cell import BuildingGraph, CellType, VerticalScope


def graph():
    g=BuildingGraph(2);g.size_prior=SizePrior()
    g.site_boundaries={f:[(-20,-20),(20,-20),(20,20),(-20,20)] for f in range(2)}
    g.site_holes={0:[],1:[]}
    g.add_node('core',0,0,scope=VerticalScope.MULTI_FLOOR,cell_type=CellType.CORE)
    g.module_bank=GraphDictionary(g)
    return g


class ExperimentTests(unittest.TestCase):
    def test_shape_certificate_catches_notch_and_enclosed_hole_without_polygons(self):
        shape=make_shape(((1.,0.,2.),(-1.,0.,2.),(0.,1.,2.),(0.,-1.,2.)),frozenset(),SizePrior())
        box=[(-5,-5),(5,-5),(5,5),(-5,5)]
        notch=[(-5,-5),(5,-5),(5,5),(1,5),(1,1),(-1,1),(-1,5),(-5,5)]
        hole=[(.5,.5),(1.,.5),(1.,1.),(.5,1.)]
        with patch('shared_modules._bounded_polygon',side_effect=AssertionError('polygon construction')):
            self.assertTrue(shape_inside_site(shape,(0,0),.2,box))
            self.assertFalse(shape_inside_site(shape,(0,0),0,notch))
            self.assertFalse(shape_inside_site(shape,(0,0),0,box,[hole]))
            self.assertTrue(shape_inside_site(shape,(3,0),0,box))
            self.assertFalse(shape_inside_site(shape,(3.01,0),0,box))

    def test_certificate_agrees_with_independent_polygon_oracle(self):
        import random
        from shapely.geometry import Polygon
        from shared_modules import _bounded_polygon,turn
        rng=random.Random(443)
        site=[(-9,-8),(8,-8),(9,7),(2,7),(2,3),(-2,3),(-2,8),(-9,8)]
        hole=[(-6,-6),(-4,-6),(-4,-4),(-6,-4)]
        prior=SizePrior()
        for _ in range(100):
            planes=tuple((math.cos(a),math.sin(a),b) for a,b in
                [(rng.uniform(-math.pi,math.pi),rng.uniform(1.3,4.)) for j in range(5)])
            shape=make_shape(planes,frozenset(),prior)
            if shape is None:continue
            local=_bounded_polygon(tuple(((x,y),b) for x,y,b in shape.planes),(),prior)
            origin=(rng.uniform(-9,9),rng.uniform(-8,8));angle=rng.uniform(-3,3)
            poly=Polygon([(x+origin[0],y+origin[1]) for x,y in (turn(p,angle) for p in local)])
            self.assertEqual(shape_inside_site(shape,origin,angle,site,[hole]),Polygon(site,[hole]).covers(poly))

    def test_boundary_inputs_change_under_boundary_change_not_translation(self):
        g=graph();g.module_bank.commit(g.module_bank.probe(4,0,0,'multi_floor')[0],'r')
        original=boundary_features(g,'cpu')
        moved=copy.deepcopy(g)
        for node in moved.nodes.values():node.x+=23;node.y-=11
        moved.site_boundaries={f:[(x+23,y-11) for x,y in loop] for f,loop in moved.site_boundaries.items()}
        self.assertTrue(torch.allclose(original,boundary_features(moved,'cpu'),atol=1e-6))
        g.site_boundaries[0]=[(-8,-8),(8,-8),(8,8),(-8,8)]
        self.assertFalse(torch.allclose(original,boundary_features(g,'cpu')))
        self.assertEqual(float(boundary_features(g,'cpu',False).abs().sum()),0.)

    def test_boundary_head_trains_and_research_checkpoint_is_explicit(self):
        g=graph();learner=ResearchLearner(boundary=True)
        before=copy.deepcopy(learner.model.boundary.state_dict())
        learner.choose(g,[[0.]*12,[1.]*12],anchors=['core','core'],positions=[(4,0),(0,4)])
        learner.finish(.7)
        self.assertTrue(any(not torch.equal(v,before[k]) for k,v in learner.model.boundary.state_dict().items()))
        state=learner.state();self.assertEqual(state['schema'],'research-boundary-1')
        loaded=ResearchLearner();loaded.load_research(state)
        self.assertEqual(loaded.updates,1)
        loaded.inference_sampling=True
        loaded.choose(g,[[0.]*12,[1.]*12],training=False,anchors=['core','core'],positions=[(4,0),(0,4)])
        self.assertEqual(loaded.trajectory,[])
        self.assertEqual(loaded.updates,1)

    def test_repair_is_transactional_and_rebuilds_full_height_footprints(self):
        g=graph();bank=g.module_bank;bank.commit(bank.probe(4,0,0,'multi_floor')[0],'r')
        old=[(n.x,n.y) for n in g.nodes.values()]
        self.assertIsNone(rebuild_after_pose(g,'r',(0,0),0))
        self.assertEqual(old,[(n.x,n.y) for n in g.nodes.values()])
        result=rebuild_after_pose(g,'r',(4.1,.1),.01)
        self.assertIsNotNone(result)
        self.assertEqual(old,[(n.x,n.y) for n in g.nodes.values()])
        audit=validate(result.module_bank.inference(),result.site_boundaries)
        self.assertTrue(audit['valid'],audit)
        self.assertEqual(len({n.area for n in result.module_bank.instances['r'].nodes}),1)

    def test_ranker_learns_only_from_training_checks(self):
        g=graph();e=GraphExperiment('ranking')
        candidates=[dict(x=4,y=0,anchor_node='core',span=4),dict(x=20,y=0,anchor_node='core',span=20)]
        e.rank(g.module_bank,0,candidates)
        e.observe(g.module_bank,0,candidates[0],True);e.observe(g.module_bank,0,candidates[1],False)
        e.finish();self.assertEqual(e.ranker.updates,1)
        frozen=GraphExperiment('ranking',training=False,ranker=e.ranker)
        frozen.observe(g.module_bank,0,candidates[0],False);frozen.finish()
        self.assertEqual(e.ranker.updates,1)

    def test_repair_acceptance_uses_same_per_floor_objective_as_training(self):
        from graph_experiments import implicit_score
        from graph_proxy import GraphSketch
        g=graph();g.module_bank.commit(g.module_bank.probe(4,0,0,'independent')[0],'r')
        areas={0:100.,1:400.}
        expected=sum(GraphSketch(g).metrics(f,areas[f],10)['score'] for f in range(2))/2
        self.assertAlmostEqual(implicit_score(g.module_bank,areas,10),expected)
