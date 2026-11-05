import math
import unittest
from graph_proxy import site_net_area


class FillDefinitionTests(unittest.TestCase):
    def test_net_area_uses_exact_polygon_not_cell_count_or_hull(self):
        site=dict(outer=[(0,0),(5,0),(5,1),(2,1),(2,4),(0,4)],
            holes=[[(.2,.2),(.7,.2),(.7,.7),(.2,.7)]],area=100000)
        self.assertAlmostEqual(site_net_area(site),10.75)
        site['exactArea']=10.75
        self.assertEqual(site_net_area(site),10.75)
        with self.assertRaises(ValueError):site_net_area(dict(area=100))

    def test_training_and_preview_use_same_exact_denominator(self):
        from server import ParallelTrainer
        t=ParallelTrainer(dict(generatorEngine='graph_voronoi',graphController='neural',
            boundaryType='rect',siteAreaTier='L',parallelEnvironments=4,maxModules=120,seed=123))
        self.addCleanup(t.executor.shutdown,wait=True)
        t.new_site()
        # Corrupting only the legacy raster descriptor must not affect graph fill.
        for env in t.environments:env.site['area']=1e9
        event=t.step(t.generation_id,t.episode)
        denominator=math.fsum(env.site['exactArea'] for env in t.environments)
        expected=math.fsum(n.area for n in t.building_graph.nodes.values())/denominator
        self.assertAlmostEqual(event['metrics']['fillRatio'],round(expected,3))
        preview=t.evaluate(t.generation_id,t.episode)
        self.assertEqual(preview['metrics']['fillRatio'],round(expected,3))
        self.assertAlmostEqual(preview['metrics']['filledArea']/preview['metrics']['siteArea'],expected,places=6)
        self.assertIn('spatialQuality',preview['validation'])
        self.assertEqual(t.graph_learner.updates,0)

    def test_multi_floor_ratio_is_ratio_of_sums_not_average_of_ratios(self):
        from server import ParallelTrainer
        from graph_proxy import GraphSketch
        # Reuse real complete metric rows so the aggregate exercises the actual
        # UI path; this is an accounting fixture, not a throughput benchmark.
        from typed_cell import BuildingGraph,CellType
        g=BuildingGraph(2);g.add_node('a',0,0,cell_type=CellType.CORE)
        g.add_node('b',0,0,floor_index=1,cell_type=CellType.CORE)
        rows=[GraphSketch(g).metrics(f,area) for f,area in enumerate((100.,400.))]
        rows[0]['filledArea']=50.;rows[1]['filledArea']=40.
        t=object.__new__(ParallelTrainer);t.dictionary=[];t.topology_multiplier=1.
        t._core_stacking_event=lambda:{}
        result=t._aggregate_terminal(rows,update_state=False)
        self.assertAlmostEqual(result['fillRatio'],.18)
        self.assertNotAlmostEqual(result['fillRatio'],.30)

    def test_independent_benchmark_uses_same_exact_weighted_fill(self):
        import sys
        from pathlib import Path
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
        from compare_graph_proposals import independent_metrics
        # An accounting fixture; geometric validity is tested independently.
        event=dict(validation=dict(valid=True,perFloor={0:dict(filledArea=50.),1:dict(filledArea=40.)}),
            placements=[dict(id='a',moduleId='m1',category='room',floor=0,poly=[(0,0),(5,0),(5,10),(0,10)]),
                dict(id='b',moduleId='m2',category='room',floor=1,poly=[(0,0),(4,0),(4,10),(0,10)])])
        sites=[dict(outer=[(0,0),(10,0),(10,10),(0,10)],holes=[]),
               dict(outer=[(0,0),(20,0),(20,20),(0,20)],holes=[])]
        metrics=independent_metrics(event,sites)
        self.assertAlmostEqual(metrics['actualFill'],.18)
        self.assertAlmostEqual(metrics['meanFloorFill'],.30)
