"""Statistical accounting tests with synthetic values, not experiment results."""
import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('comparison',Path(__file__).resolve().parents[1]/'tools/compare_graph_architectures.py')
comparison=importlib.util.module_from_spec(spec);spec.loader.exec_module(comparison)


class ComparisonTests(unittest.TestCase):
    def row(self,arch,seed,index,value,phase='validation',valid=True):
        return dict(architecture=arch,initializationSeed=seed,phase=phase,index=index,
            siteFingerprint=str(index),verifiedOutcome=value,valid=valid,actualFill=.5,reuseRatio=.8)

    def test_pilot_cannot_pass_promotion_gate(self):
        records=[self.row('message_passing',123,i,0.) for i in range(2)]
        records += [self.row('local_message_passing',123,i,.2) for i in range(2)]
        result=comparison.paired_summary(records)
        self.assertFalse(result['architectures']['local_message_passing']['validationCandidate'])
        self.assertEqual(result['promotion'],'not_performed')

    def test_errors_are_not_removed_from_mean(self):
        rows=[self.row('message_passing',123,0,0.),dict(architecture='message_passing',initializationSeed=123,phase='validation',index=1,error='failed')]
        result=comparison.paired_summary(rows)['architectures']['message_passing']
        self.assertEqual(result['cases'],2);self.assertEqual(result['errors'],1)
        self.assertIsNone(result['meanOutcome'])

    def test_pairing_requires_same_actual_site_and_initialization(self):
        rows=[self.row('message_passing',123,0,0.),self.row('local_message_passing',456,0,.2)]
        stats=comparison.paired_summary(rows)['architectures']['local_message_passing']
        self.assertEqual(stats['pairedCases'],0)
        self.assertFalse(stats['validationCandidate'])

    def test_pre_post_evaluation_retained_separately(self):
        rows=[self.row('message_passing',123,0,-.2,'initial_validation'),self.row('message_passing',123,0,.1)]
        stats=comparison.paired_summary(rows)['architectures']['message_passing']
        self.assertAlmostEqual(stats['meanChangeFromUntrained'],.3)

    def test_enough_pairs_still_requires_all_initializations_improve(self):
        rows=[]
        for seed in (123,456,789):
            for i in range(24):
                rows.append(self.row('message_passing',seed,i,0.))
                rows.append(self.row('local_message_passing',seed,i,.2 if seed!=789 else -.2))
        self.assertFalse(comparison.paired_summary(rows)['architectures']['local_message_passing']['validationCandidate'])

    def test_positive_candidate_requires_real_post_training_gain(self):
        rows=[]
        for seed in (123,456,789):
            for i in range(24):
                rows.extend([self.row('message_passing',seed,i,0.),
                             self.row('local_message_passing',seed,i,.2),
                             self.row('local_message_passing',seed,i,.2,'initial_validation')])
        self.assertFalse(comparison.paired_summary(rows)['architectures']['local_message_passing']['validationCandidate'])
        for r in rows:
            if r['phase']=='initial_validation':r['verifiedOutcome']=-.1
        self.assertTrue(comparison.paired_summary(rows)['architectures']['local_message_passing']['validationCandidate'])

    def test_simplifying_to_underfilled_layout_cannot_pass(self):
        rows=[]
        for seed in (123,456,789):
            for i in range(24):
                rows.extend([self.row('message_passing',seed,i,0.),
                             self.row('local_message_passing',seed,i,.2),
                             self.row('local_message_passing',seed,i,-.1,'initial_validation')])
        for r in rows:
            if r['architecture']=='local_message_passing':r['actualFill']=.1
        self.assertFalse(comparison.paired_summary(rows)['architectures']['local_message_passing']['validationCandidate'])
