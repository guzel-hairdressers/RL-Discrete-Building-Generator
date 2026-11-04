"""Network wiring and lifecycle tests; no convergence/throughput claims."""
import copy
import io
import tempfile
import unittest
from unittest.mock import patch
import torch
from typed_cell import BuildingGraph, CellType
from graph_policy import GraphLearner


class GraphPolicyTests(unittest.TestCase):
    def fixture(self):
        graph=BuildingGraph(1)
        graph.add_node('core',0,0,cell_type=CellType.CORE)
        graph.add_node('room',4,0);graph.add_edge('core','room')
        features=[[i/10 for i in range(10)],[1-i/10 for i in range(10)],[.2]*10]
        return graph,features

    def test_actor_critic_and_encoder_really_update(self):
        g,f=self.fixture(); learner=GraphLearner(seed=7)
        before={k:v.clone() for k,v in learner.model.state_dict().items()}
        for _ in range(3):learner.choose(g,f)
        stats=learner.finish(.7)
        changed={k for k,v in learner.model.state_dict().items() if not torch.equal(v,before[k])}
        self.assertTrue(any(k.startswith('actor.') for k in changed))
        self.assertTrue(any(k.startswith('critic.') for k in changed))
        self.assertTrue(any(k.startswith('message.') for k in changed))
        self.assertEqual(stats['policyUpdateCount'],1)
        self.assertGreater(stats['gradientNorm'],0.)
        self.assertEqual(stats['stochasticDecisionCount'],3)

    def test_inference_does_not_change_weights_or_optimizer(self):
        g,f=self.fixture();learner=GraphLearner()
        before=copy.deepcopy(learner.state())
        choices=[learner.choose(g,f,False) for _ in range(3)]
        self.assertEqual(len(set(choices)),1)
        learner.finish(.8,False)
        self.assertEqual(learner.updates,0)
        self.assertFalse(learner.optimizer.state)
        for k,v in learner.model.state_dict().items():self.assertTrue(torch.equal(v,before['model'][k]))
        self.assertEqual(learner.trajectory,[])

    def test_empty_episode_no_fake_update(self):
        learner=GraphLearner(); stats=learner.finish(-1.)
        self.assertEqual(stats['policyUpdateCount'],0)
        self.assertEqual(stats['policyDecisionCount'],0)

    def test_seed_isolated_and_checkpoint_replays_sampling(self):
        before=torch.random.get_rng_state().clone(); learner=GraphLearner(seed=17)
        self.assertTrue(torch.equal(before,torch.random.get_rng_state()))
        g,f=self.fixture();learner.choose(g,f);learner.finish(.5)
        saved=copy.deepcopy(learner.state());other=GraphLearner();other.load(saved)
        self.assertEqual([learner.choose(g,f) for _ in range(5)],[other.choose(g,f) for _ in range(5)])
        self.assertEqual(other.updates,1)

    def test_nonfinite_reward_rejected_and_tape_cleared(self):
        learner=GraphLearner(); g,f=self.fixture();learner.choose(g,f)
        with self.assertRaises(ValueError):learner.finish(float('nan'))
        self.assertFalse(learner.trajectory)


class TrainableDemoIntegrationTests(unittest.TestCase):
    def trainer(self):
        from server import ParallelTrainer
        return ParallelTrainer({'generatorEngine':'graph_voronoi','graphController':'neural',
            'boundaryType':'rect','siteAreaTier':'L','parallelEnvironments':4,'maxModules':10,'seed':123})

    def episode(self,t):
        for _ in range(25):
            event=t.step(t.generation_id,t.episode)
            if event['type']=='episodeDone': return event
        self.fail('test episode did not terminate')

    def test_live_trainer_trains_persists_and_infers(self):
        t=self.trainer();t.new_site()
        before={k:v.clone() for k,v in t.graph_learner.model.state_dict().items()}
        event=self.episode(t);metrics=event['metrics']
        self.assertEqual(metrics['learningAlgorithm'],'graph_actor_critic_experimental')
        self.assertGreater(metrics['policyUpdateCount'],0)
        self.assertGreater(metrics['stochasticDecisionCount'],0)
        self.assertTrue(any(not torch.equal(v,before[k]) for k,v in t.graph_learner.model.state_dict().items()))
        self.assertIn('valid',event['validation'])
        self.assertEqual(event['validation']['valid'],metrics['geometryValid'])
        after={k:v.clone() for k,v in t.graph_learner.model.state_dict().items()}
        t.new_site()
        for k,v in t.graph_learner.model.state_dict().items():self.assertTrue(torch.equal(v,after[k]))
        t.set_mode('inference');event=self.episode(t)
        self.assertEqual(event['metrics']['learningAlgorithm'],'graph_inference')
        for k,v in t.graph_learner.model.state_dict().items():self.assertTrue(torch.equal(v,after[k]))

    def test_server_checkpoint_roundtrip_and_corruption_rollback(self):
        t=self.trainer();t.new_site();self.episode(t)
        with tempfile.TemporaryDirectory() as directory:
            with patch('server.OUTPUT_DIR',directory):path=t.save_checkpoint()
            from pathlib import Path
            data=Path(path).read_bytes()
        restored=self.trainer();restored.load_checkpoint_data(data)
        self.assertEqual(restored.graph_learner.updates,t.graph_learner.updates)
        for k,v in t.graph_learner.model.state_dict().items():self.assertTrue(torch.equal(v,restored.graph_learner.model.state_dict()[k]))
        raw=torch.load(io.BytesIO(data),weights_only=True)
        first=next(iter(raw['graphLearner']['model']))
        raw['graphLearner']['model'][first].fill_(float('nan'))
        stream=io.BytesIO();torch.save(raw,stream)
        before=copy.deepcopy(restored.graph_learner.state())
        with self.assertRaises(ValueError):restored.load_checkpoint_data(stream.getvalue())
        for k,v in restored.graph_learner.model.state_dict().items():self.assertTrue(torch.equal(v,before['model'][k]))

    def test_mode_change_drops_partial_training_graph(self):
        t=self.trainer();t.new_site();t.step(t.generation_id,t.episode)
        self.assertGreater(len(t.graph_learner.trajectory),0)
        t.set_mode('inference');self.assertEqual(t.graph_learner.trajectory,[])

class ContactNumericsTests(unittest.TestCase):
    def test_contact_tolerance_does_not_bridge_real_gaps(self):
        from types import SimpleNamespace as NS
        from shared_modules import contact_pairs, SizePrior
        for gap,expected in [(1e-9,1),(.001,0)]:
            nodes=[NS(node_id='a',floor_index=0,cell_type=CellType.ROOM),NS(node_id='b',floor_index=0,cell_type=CellType.ROOM)]
            polys={'a':[(0,0),(1,0),(1,1),(0,1)],'b':[(1+gap,0),(2+gap,0),(2+gap,1),(1+gap,1)]}
            result=NS(occurrences={n.node_id:NS(prototype='p',nodes=[n]) for n in nodes},
                      polygon=lambda oid:polys[oid],prior=SizePrior())
            contacts,access=contact_pairs(result)
            self.assertEqual(len(contacts),expected)
            self.assertEqual(len(access),expected)

class ArchitectureTests(unittest.TestCase):
    def fixture(self):
        g=BuildingGraph(1)
        g.add_node('core',0,0,cell_type=CellType.CORE)
        g.add_node('room',4,0);g.add_edge('core','room')
        return g,[[.1]*10,[.2]*10],['core','room']

    def test_every_architecture_trains_and_checkpoint_restores_type(self):
        from graph_policy import ARCHITECTURES
        g,f,anchors=self.fixture()
        for architecture in ARCHITECTURES:
            with self.subTest(architecture=architecture):
                learner=GraphLearner(architecture=architecture)
                learner.choose(g,f,anchors=anchors,positions=[(4,2),(0,5)])
                stats=learner.finish(.5)
                self.assertEqual(stats['architecture'],architecture)
                self.assertGreater(stats['gradientNorm'],0)
                restored=GraphLearner();restored.load(copy.deepcopy(learner.state()))
                self.assertEqual(restored.model.architecture,architecture)
                self.assertEqual(learner.choose(g,f,False,anchors,[(4,2),(0,5)]),restored.choose(g,f,False,anchors,[(4,2),(0,5)]))

    def test_local_actor_distinguishes_anchors_for_equal_proposal_features(self):
        from graph_policy import encode_graph
        g,f,anchors=self.fixture();learner=GraphLearner(architecture='local_message_passing')
        with torch.no_grad():
            logits,_=learner.model(*encode_graph(g,'cpu'),torch.tensor([[.1]*10]*2),torch.tensor([0,1]))
        self.assertNotEqual(float(logits[0]),float(logits[1]))

    def test_local_encoder_invariant_to_node_relabel_and_insertion(self):
        from graph_policy import encode_graph
        g,f,anchors=self.fixture();other=BuildingGraph(1)
        other.add_node('new_room',4,0);other.add_node('new_core',0,0,cell_type=CellType.CORE)
        other.add_edge('new_core','new_room')
        learner=GraphLearner(architecture='local_message_passing')
        with torch.no_grad():
            a,_=learner.model(*encode_graph(g,'cpu'),torch.tensor(f),torch.tensor([0,1]))
            b,_=learner.model(*encode_graph(other,'cpu'),torch.tensor(f),torch.tensor([1,0]))
        self.assertTrue(torch.allclose(a,b,atol=1e-6))

    def test_old_schema_one_loads_baseline(self):
        learner=GraphLearner();state=learner.state();state['schema']=1;state.pop('architecture')
        restored=GraphLearner(architecture='local_message_passing');restored.load(state)
        self.assertEqual(restored.model.architecture,'message_passing')

    def test_invalid_geometry_cannot_outscore_a_valid_low_score(self):
        from graph_policy import outcome_reward
        for score in (-500,-200,-35,0,100):
            self.assertGreater(outcome_reward(score,True),outcome_reward(score,False))
        self.assertLess(outcome_reward(-35,True),outcome_reward(0,True))

class CandidateAttentionTests(unittest.TestCase):
    def test_attention_trains_and_is_rigid_frame_invariant(self):
        from graph_policy import encode_graph,relative_candidate_geometry
        from shared_modules import turn
        g=BuildingGraph(1)
        g.add_node('c',0,0,cell_type=CellType.CORE);g.add_node('r',4,0);g.add_edge('c','r')
        positions=[(4,2),(0,5)];anchors=torch.tensor([0,1])
        theta=.713
        rotated=BuildingGraph(1)
        for n in g.nodes.values():
            x,y=turn((n.x,n.y),theta)
            rotated.add_node(n.node_id,x+13,y-17,cell_type=n.cell_type)
        rotated.add_edge('c','r')
        new_positions=[(x+13,y-17) for x,y in (turn(p,theta) for p in positions)]
        a=relative_candidate_geometry(g,anchors,positions,'cpu')
        b=relative_candidate_geometry(rotated,anchors,new_positions,'cpu')
        self.assertTrue(torch.allclose(a,b,atol=1e-6))
        learner=GraphLearner(architecture='candidate_attention')
        features=[[.1]*10,[.2]*10]
        with torch.no_grad():
            logits,_=learner.model(*encode_graph(g,'cpu'),torch.tensor(features),anchors,a)
            new_logits,_=learner.model(*encode_graph(rotated,'cpu'),torch.tensor(features),anchors,b)
        self.assertTrue(torch.allclose(logits,new_logits,atol=1e-6))
        before=learner.model.attention[0].weight.clone()
        learner.choose(g,features,anchors=['c','r'],positions=positions);learner.finish(.7)
        self.assertFalse(torch.equal(before,learner.model.attention[0].weight))

    def test_missing_geometric_inputs_rejected(self):
        learner=GraphLearner(architecture='candidate_attention');g=BuildingGraph(1);g.add_node('a',0,0)
        with self.assertRaises(ValueError):learner.choose(g,[[0.]*10],anchors=['a'])

class ArchitectureServerLifecycleTests(unittest.TestCase):
    def trainer(self):
        from server import ParallelTrainer
        return ParallelTrainer({'generatorEngine':'graph_voronoi','boundaryType':'rect',
            'siteAreaTier':'L','parallelEnvironments':4,'maxModules':10})

    def test_architecture_change_resets_only_when_changed(self):
        t=self.trainer();g=BuildingGraph(1);g.add_node('c',0,0,cell_type=CellType.CORE)
        t.graph_learner.choose(g,[[.1]*10,[.2]*10]);t.graph_learner.finish(.5)
        old=t.graph_learner
        t.new_site();self.assertIs(t.graph_learner,old)
        self.assertEqual(t.graph_learner.updates,1)
        t.update_settings({'graphPolicyArchitecture':'local_message_passing'})
        self.assertEqual(t.graph_learner.model.architecture,'local_message_passing')
        self.assertEqual(t.graph_learner.updates,0)
        local=t.graph_learner;t.new_site();self.assertIs(t.graph_learner,local)

    def test_local_checkpoint_can_load_into_baseline_session(self):
        t=self.trainer();t.update_settings({'graphPolicyArchitecture':'local_message_passing'})
        with tempfile.TemporaryDirectory() as directory:
            with patch('server.OUTPUT_DIR',directory):path=t.save_checkpoint()
            from pathlib import Path
            data=Path(path).read_bytes()
        other=self.trainer();other.load_checkpoint_data(data)
        self.assertEqual(other.graph_learner.model.architecture,'local_message_passing')
        self.assertEqual(other.settings['graphPolicyArchitecture'],'local_message_passing')
        before=other.graph_learner
        other.new_site();self.assertIs(other.graph_learner,before)

    def test_candidate_attention_runs_real_training_episode(self):
        t=self.trainer();t.update_settings({'graphPolicyArchitecture':'candidate_attention'})
        for _ in range(25):
            event=t.step(t.generation_id,t.episode)
            if event['type']=='episodeDone':break
        else:self.fail('attention integration episode did not finish')
        self.assertEqual(event['metrics']['architecture'],'candidate_attention')
        self.assertGreater(event['metrics']['policyUpdateCount'],0)
        self.assertGreater(event['metrics']['gradientNorm'],0)
