import math
import unittest
from graph_windows import cone_distance,allocate,required_frontage
from plot_directions import descriptors,features,candidates
from typed_cell import BuildingGraph,CellType
from graph_dictionary import GraphDictionary
from shared_modules import SizePrior


def window(oid,x,y=0.,normal=(1.,0.),length=2.):
    nx,ny=normal
    return dict(occurrenceId=oid,segment=[[x+ny*length/2,y-nx*length/2],[x-ny*length/2,y+nx*length/2]],
                normal=list(normal),length=length,skyShare=1.)


class WindowRulesTests(unittest.TestCase):
    def test_impossible_junction_cut_is_rejected_before_shape_solving(self):
        from unittest.mock import patch
        from test_graph_spatial import scene
        from graph_proxy import SpatialNodes
        _,bank=scene(gap=20.,floors=1)
        bank.spatial=SpatialNodes(bank.graph,bank.prior.radius)
        bank.protected_junctions['module_1']=((2.,2.),)
        with patch('graph_dictionary.shape_with',side_effect=AssertionError('unnecessary prototype solve')):
            self.assertEqual(bank.probe(3.,3.,0,'independent',preferred_pid='module_1',preferred_angle=0.),[])

    def test_graph_training_uses_only_proxy_budgets_not_realized_edge_allocator(self):
        from unittest.mock import patch
        from test_graph_spatial import scene
        from graph_spatial import evidence
        _,bank=scene(gap=20.)
        with patch('graph_windows.allocate',side_effect=AssertionError('exact glazing allocation during graph training')):
            row=evidence(bank).metrics(0)
        self.assertEqual(row['windowPlan']['status'],'graph_frontage_privacy_proxy')
        self.assertEqual(row['windowPlan']['windows'],[])
        self.assertTrue(row['rooms'][0]['unknownWindows'])

    def test_realized_openings_use_complete_edges_and_core_is_solid(self):
        from test_graph_spatial import scene
        from realized_spatial import RealizedSpatialEvidence
        _,bank=scene(gap=20.)
        actual=RealizedSpatialEvidence(bank.inference()).metrics(3)
        windows=actual['windowPlan']['windows']
        self.assertTrue(windows)
        self.assertTrue(all(w['occurrenceId']=='room' and abs(w['length']-4.)<1e-6 for w in windows))
        self.assertEqual(actual['windowPlan']['violations'],[])
        self.assertEqual(actual['rooms'][0]['requiredWindowFrontage'],2*16/15)

    def test_legacy_policy_and_adam_moments_migrate_without_losing_values(self):
        import copy,torch
        from graph_policy import GraphLearner
        g=BuildingGraph(1);g.add_node('core',0.,0.,cell_type=CellType.CORE)
        source=GraphLearner(seed=12);source.choose(g,[[0.]*12,[1.]*12]);source.finish(.5)
        state=copy.deepcopy(source.state());state['schema']=4
        state['model']={k:v for k,v in state['model'].items() if not k.startswith(('plot_encoder.','plot_actor.'))}
        state['optimizer']['param_groups'][0]['params']=state['optimizer']['param_groups'][0]['params'][:-8]
        kept=set(state['optimizer']['param_groups'][0]['params'])
        state['optimizer']['state']={k:v for k,v in state['optimizer']['state'].items() if k in kept}
        migrated=GraphLearner();migrated.load(state)
        for k,v in state['model'].items():self.assertTrue(torch.equal(v,migrated.model.state_dict()[k]))
        for parameter,values in state['optimizer']['state'].items():
            for name,value in values.items():self.assertTrue(torch.equal(value,migrated.optimizer.state_dict()['state'][parameter][name]))

    def test_plot_conditioning_receives_training_gradients(self):
        import torch
        from graph_policy import GraphLearner
        g=PlotDirectionsTests().graph([(-30.,-5.),(30.,-5.),(30.,5.),(-30.,5.)])
        learner=GraphLearner(seed=15)
        before=learner.model.plot_actor[-1].weight.detach().clone()
        learner.choose(g,[[0.]*12,[0.]*12],anchors=['core','core'],positions=[(5.,0.),(0.,5.)]);learner.finish(.8)
        self.assertFalse(torch.equal(before,learner.model.plot_actor[-1].weight))

    def test_cached_policy_edges_preserve_order_lengths_and_previous_tapes(self):
        import torch
        from graph_policy import encode_graph
        from typed_cell import VerticalScope
        g=BuildingGraph(4);g.add_node('core',0.,0.,cell_type=CellType.CORE,scope=VerticalScope.MULTI_FLOOR)
        old=None
        for j in range(1,6):
            g.add_node(str(j),j*4.,0.,scope=VerticalScope.MULTI_FLOOR)
            for floor in range(4):
                a='core' if floor==0 else f'core_f{floor:02d}'
                b=str(j) if floor==0 else f'{j}_f{floor:02d}'
                g.add_edge(a,b)
            _,edges,lengths=encode_graph(g,'cpu')
            ids={nid:k for k,nid in enumerate(g.nodes)};pairs=[];distances=[]
            for e in g.edges_horiz+g.edges_vert:
                d=math.dist(g.nodes[e.u].pos3d,g.nodes[e.v].pos3d)/9.
                pairs.extend(((ids[e.u],ids[e.v]),(ids[e.v],ids[e.u])));distances.extend(([d],[d]))
            self.assertTrue(torch.equal(edges,torch.tensor(pairs).T))
            self.assertTrue(torch.equal(lengths,torch.tensor(distances)))
            if old is not None:self.assertTrue(torch.equal(old[0],old[1]))
            old=edges,edges.clone()
        g.nodes['1'].x+=.75;g.pose_revision=1
        _,_,changed=encode_graph(g,'cpu')
        self.assertFalse(torch.equal(lengths,changed))

    def test_area_scaled_frontage(self):
        self.assertEqual(required_frontage(10.),2.)
        self.assertEqual(required_frontage(15.),2.)
        self.assertEqual(required_frontage(30.),4.)
        self.assertAlmostEqual(required_frontage(22.5),3.)

    def test_cone_distance_is_not_midpoint_or_origin_distance(self):
        a=window('a',0.)
        self.assertAlmostEqual(cone_distance(a['segment'],window('b',25.)['segment'],(1.,0.)),25.)
        self.assertEqual(cone_distance(a['segment'],window('b',-1.)['segment'],(1.,0.)),math.inf)
        self.assertEqual(cone_distance(a['segment'],window('b',10.,20.)['segment'],(1.,0.)),math.inf)
        # Centre is outside ±30°, but the end of the long interval enters it.
        self.assertLess(cone_distance(a['segment'],window('b',10.,8.,length=10.)['segment'],(1.,0.)),25.)

    def test_selected_windows_not_blank_facades_are_privacy_targets(self):
        a,b=window('a',0.),window('b',10.,normal=(-1.,0.))
        # Only one side can carry a facing opening below25m.
        result=allocate([a,b],{'a':2.,'b':2.})
        self.assertEqual(sum(result['frontage'].values()),2.)
        self.assertEqual(result['conflictPairs'],1)
        self.assertEqual(allocate([a],{'a':2.})['frontage']['a'],2.)
        b=window('b',25.,normal=(-1.,0.))
        self.assertEqual(sum(allocate([a,b],{'a':2.,'b':2.})['frontage'].values()),4.)

    def test_whole_edges_are_not_trimmed_to_the_required_frontage(self):
        slots=[window('a',0.,k,length=.8) for k in (0.,1.,2.)]
        result=allocate(slots,{'a':2.})
        self.assertAlmostEqual(sum(w['length'] for w in result['windows']),2.4)
        self.assertEqual(len(result['windows']),3)

    def test_cone_rotation_and_translation(self):
        a,b=window('a',0.),window('b',20.,3.,normal=(-1.,0.))
        theta=.716;c,s=math.cos(theta),math.sin(theta)
        transform=lambda p:[c*p[0]-s*p[1]+178.,s*p[0]+c*p[1]-81.]
        self.assertAlmostEqual(cone_distance(a['segment'],b['segment'],(1.,0.)),
            cone_distance(list(map(transform,a['segment'])),list(map(transform,b['segment'])),(c,s)))


class PlotDirectionsTests(unittest.TestCase):
    def graph(self,poly):
        g=BuildingGraph(1);g.size_prior=SizePrior();g.site_boundaries={0:poly}
        g.add_node('core',0.,0.,cell_type=CellType.CORE)
        g.module_bank=GraphDictionary(g)
        return g

    def test_triangle_retains_three_edge_directions(self):
        g=self.graph([(0.,0.),(40.,0.),(13.,21.)])
        d=descriptors(g,0)
        self.assertEqual(len(d['axes']),3)
        self.assertAlmostEqual(sum(a['weight'] for a in d['axes']),1.)

    def test_narrow_rectangle_and_subdivision_invariance(self):
        a=self.graph([(-50.,-5.),(50.,-5.),(50.,5.),(-50.,5.)])
        b=self.graph([(-50.,-5.),(0.,-5.),(50.,-5.),(50.,5.),(-50.,5.)])
        self.assertAlmostEqual(descriptors(a,0)['aspectRatio'],10.)
        self.assertEqual(descriptors(a,0),descriptors(b,0))
        self.assertEqual(features(a,0,(0,0),(10,0)),features(b,0,(0,0),(10,0)))
        self.assertTrue(candidates(a.module_bank,0))

    def test_policy_features_rotate_with_site(self):
        poly=[(-10.,-4.),(10.,-4.),(13.,4.),(-8.,6.)]
        theta=.61;c,s=math.cos(theta),math.sin(theta)
        r=lambda p:(c*p[0]-s*p[1]+91,s*p[0]+c*p[1]-17)
        a=self.graph(poly);b=self.graph(list(map(r,poly)))
        for x,y in zip(features(a,0,(0,0),(6,2)),features(b,0,r((0,0)),r((6,2)))):self.assertAlmostEqual(x,y,places=6)
