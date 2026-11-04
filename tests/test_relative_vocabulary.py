"""Observed-angle and continuous-action correctness, not performance benchmarks."""
import copy
import math
from pathlib import Path
import unittest
import torch
from graph_policy import GraphLearner,encode_graph
from graph_dictionary import GraphDictionary
from relative_vocabulary import RelativeVocabulary
from shared_modules import SizePrior
from typed_cell import BuildingGraph,CellType


class RelativeVocabularyTests(unittest.TestCase):
    def fixture(self,rotation=0.,translation=(0,0),prefix=''):
        g=BuildingGraph(1);g.add_node(prefix+'c',*translation,cell_type=CellType.CORE)
        for i,(bearing,length) in enumerate(((.2,4.1),(.9,5.3),(2.,6.2))):
            a=bearing+rotation;g.add_node(prefix+str(i),translation[0]+length*math.cos(a),translation[1]+length*math.sin(a))
            g.add_edge(prefix+'c',prefix+str(i))
        v=RelativeVocabulary();v.observe(g,g.nodes)
        return g,v

    def test_pairwise_turns_include_composite_turn_and_wrapped_complement(self):
        _,v=self.fixture()
        for angle in (.7,1.1,1.8,2*math.pi-1.8):self.assertIn(round(angle,8),v.angles)
        self.assertEqual(len(v.angles),6)
        self.assertNotIn(round(math.pi/2,8),v.angles)
        self.assertEqual(set(v.lengths),{4.1,5.3,6.2})

    def test_observation_is_idempotent_and_rigid_motion_and_labels_do_not_change_values(self):
        g,v=self.fixture();uses=dict(v.angle_uses);v.observe(g,g.nodes)
        self.assertEqual(uses,dict(v.angle_uses))
        _,other=self.fixture(.713,(12,-19),'renamed_')
        self.assertEqual(set(v.angles),set(other.angles));self.assertEqual(set(v.lengths),set(other.lengths))

    def bank(self):
        g=BuildingGraph(1);g.size_prior=SizePrior();g.add_node('c',0,0,cell_type=CellType.CORE)
        g.module_bank=GraphDictionary(g,15)
        return g,g.module_bank

    def test_dictionary_proposals_use_observations_without_inventing_turns_or_lengths(self):
        g,bank=self.bank();bank.commit(bank.probe(4.1,0,0,'independent')[0],'a')
        # The growth state records actual edge lengths; there is no angle yet.
        self.assertEqual(bank.vocabulary.candidates(bank,0),[])
        angle=.92;x,y=4.8*math.cos(angle),4.8*math.sin(angle)
        plans=bank.probe(x,y,0,'independent')
        self.assertTrue(plans);bank.commit(plans[-1],'b')
        rows=bank.vocabulary.candidates(bank,0)
        self.assertTrue(rows)
        for row in rows:
            self.assertIn(round(row['span'],8),bank.vocabulary.lengths)
            self.assertIn(round(row['relativeAngle'],8),bank.vocabulary.angles)
            n=g.nodes[row['anchor_node']]
            self.assertAlmostEqual(math.hypot(row['x']-n.x,row['y']-n.y),row['span'])

    def test_learned_continuous_head_updates_and_inference_is_frozen(self):
        g,bank=self.bank();learner=GraphLearner(seed=57)
        before={k:v.clone() for k,v in learner.model.proposal.state_dict().items()}
        for _ in range(3):
            rows=learner.propose_continuous(bank,0)
            self.assertTrue(all(r['source']=='neural_continuous' for r in rows))
            self.assertTrue(all(2.5<r['span']<9. for r in rows))
        stats=learner.finish(.7)
        self.assertGreater(stats['continuousProposalCount'],0)
        self.assertTrue(any(not torch.equal(v,before[k]) for k,v in learner.model.proposal.state_dict().items()))
        state=copy.deepcopy(learner.state());other=GraphLearner();other.load(state)
        a=learner.propose_continuous(bank,0);b=other.propose_continuous(bank,0)
        self.assertEqual(a,b)
        frozen=copy.deepcopy(other.state())
        a=other.propose_continuous(bank,0,False);b=other.propose_continuous(bank,0,False)
        self.assertEqual(a,b)
        for k,v in other.model.state_dict().items():self.assertTrue(torch.equal(v,frozen['model'][k]))
        self.assertEqual(other.updates,frozen['updates'])

    def test_real_old_checkpoint_preserves_logits_and_adam_and_can_train_new_head(self):
        fixture=torch.load(Path(__file__).parent/'fixtures/graph_policy_schema2.pt',weights_only=True)
        g,bank=self.bank();features=[[.1]*10,[.2]*10]
        restored=GraphLearner();restored.load(copy.deepcopy(fixture['state']))
        with torch.no_grad():
            logits,_=restored.model(*encode_graph(g,'cpu'),torch.tensor(features))
        self.assertTrue(torch.allclose(fixture['referenceLogits'],logits,atol=1e-7))
        self.assertEqual(fixture['state']['updates'],restored.updates)
        self.assertTrue(restored.optimizer.state)
        restored.propose_continuous(bank,0);restored.choose(g,features)
        restored.finish(.7)
        self.assertEqual(restored.updates,2)

    def test_new_angle_can_reuse_a_length_without_crediting_an_unused_length_draw(self):
        g,bank=self.bank();bank.commit(bank.probe(4.1,0,0,'independent')[0],'a')
        learner=GraphLearner(seed=71)
        before=learner.model.proposal[2].weight.detach().clone()
        rows=learner.propose_continuous(bank,0,limit=1,use_vocabulary=True)
        self.assertEqual(rows[0]['lengthSource'],'observed')
        self.assertEqual(rows[0]['angleSource'],'neural')
        self.assertIn(round(rows[0]['span'],8),bank.vocabulary.lengths)
        learner.finish(.7)
        after=learner.model.proposal[2].weight.detach()
        self.assertTrue(torch.equal(before[[1,3]],after[[1,3]]))
        self.assertFalse(torch.equal(before[[0,2]],after[[0,2]]))
