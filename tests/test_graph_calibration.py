"""Verify evaluator accounting without claiming generalization accuracy."""
import unittest
import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('graph_calibration',Path(__file__).resolve().parents[1]/'tools/evaluate_graph_proxies.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class CalibrationTests(unittest.TestCase):
    def test_bad_cases_are_retained(self):
        result=module.evaluate({'split':'held_out','cases':[{'id':'bad','floors':1,'nodes':[],'edges':[['missing','other']],'boundaries':{}}]})
        self.assertEqual(result['failedCases'],1)
        self.assertEqual(result['rows'][0]['case'],'bad')
        self.assertIsNone(result['areaMAE'])

    def test_manifest_must_declare_holdout(self):
        with self.assertRaises(ValueError):module.evaluate({'split':'training','cases':[]})

    def test_raw_prediction_and_invalidity_are_separate(self):
        result=module.evaluate({'split':'held_out','cases':[{'id':'outside','floors':1,
            'nodes':[{'id':'c','x':0,'y':0,'function':'core'}],'edges':[],
            'boundaries':{'0':[[-1,-1],[1,-1],[1,1],[-1,1]]}}]})
        row=result['rows'][0]
        self.assertFalse(row['valid'])
        self.assertGreater(row['predictedArea'],4.)
        self.assertAlmostEqual(row['predictedArea'],row['actualArea']) # Geometry not clipped to conceal invalidity.
        self.assertIsNone(result['pairwiseRankingAgreement'])
