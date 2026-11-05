import unittest
from shapely.geometry import Polygon,box
from layout_gaps import audit_floor_gaps


class GapAuditTests(unittest.TestCase):
    def ring(self):return [box(-3,-3,-1,3),box(1,-3,3,3),box(-1,-3,1,-1),box(-1,1,1,3)]

    def test_high_fill_ring_is_not_a_gap_free_floor_plate(self):
        built=self.ring();report=audit_floor_gaps(box(-3,-3,3,3),built)
        self.assertGreater(sum(p.area for p in built)/36,.88)
        self.assertFalse(report['noUnplannedEnclosedGaps'])
        self.assertEqual(report['unplannedEnclosedGapCount'],1)
        self.assertAlmostEqual(report['unplannedEnclosedGapArea'],4.,places=5)
        self.assertAlmostEqual(report['gaps'][0]['approximateLargestInscribedDiameter'],2.,places=4)

    def test_only_explicitly_planned_void_or_site_hole_is_exempt(self):
        site=box(-3,-3,3,3);hole=box(-1,-1,1,1)
        self.assertTrue(audit_floor_gaps(site,self.ring(),[hole])['noUnplannedEnclosedGaps'])
        self.assertTrue(audit_floor_gaps(site.difference(hole),self.ring())['noUnplannedEnclosedGaps'])
        self.assertFalse(audit_floor_gaps(site,self.ring(),[box(-1,-1,0,1)])['noUnplannedEnclosedGaps'])

    def test_open_unfilled_plot_is_not_counted_as_an_enclosed_hole(self):
        report=audit_floor_gaps(box(-10,-10,10,10),[box(-2,-2,2,2)])
        self.assertTrue(report['noUnplannedEnclosedGaps'])

    def test_numeric_seam_cannot_hide_a_real_gap_or_add_credited_area(self):
        built=self.ring();built[0]=box(-3,-3,-1-1e-8,3)
        before=[p.wkb for p in built];report=audit_floor_gaps(box(-4,-4,4,4),built)
        self.assertFalse(report['noUnplannedEnclosedGaps'])
        self.assertEqual(before,[p.wkb for p in built]);self.assertFalse(report['changesFootprints'])
