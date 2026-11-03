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
