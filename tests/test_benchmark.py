"""Focused tests for the subprocess-isolated performance benchmark."""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest


BENCHMARK_PATH = Path(__file__).resolve().parents[1] / "scratch" / "benchmark.py"
SPEC = importlib.util.spec_from_file_location("module_lab_benchmark", BENCHMARK_PATH)
assert SPEC is not None and SPEC.loader is not None
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


FAKE_SERVER = r'''
SCORE_OFFSET = __SCORE_OFFSET__


class _Device:
    type = "cpu"


class _Cuda:
    @staticmethod
    def manual_seed_all(seed):
        return None


class _Torch:
    __version__ = "fake-torch"
    cuda = _Cuda()

    @staticmethod
    def manual_seed(seed):
        return None


torch = _Torch()


class _Executor:
    def __init__(self):
        self.closed = False

    def shutdown(self, wait=True, cancel_futures=True):
        self.closed = True


POLY = [
    {"x": 0.0, "y": 0.0},
    {"x": 2.0, "y": 0.0},
    {"x": 2.0, "y": 1.0},
    {"x": 0.0, "y": 1.0},
]


def module(episode):
    return {
        "id": "room-" + str(episode),
        "category": "room",
        "family": "rect",
        "triangle": False,
        "poly": POLY,
    }


def placement(episode):
    return {
        "id": "floor0-p" + str(episode),
        "instanceIdx": 0,
        "module": module(episode),
        "rotation": 0.0,
        "area": 2.0,
        "neighbors": [],
        "poly": POLY,
    }


class ParallelTrainer:
    def __init__(self):
        self.device = _Device()
        self.executor = _Executor()
        self.generation_id = 0
        self.episode = 0
        self._step = 0

    def update_settings(self, settings):
        self.settings = dict(settings)
        self.generation_id += 1
        return {"type": "site"}

    def step(self, generation_id, episode):
        assert generation_id == self.generation_id
        assert episode == self.episode
        current = self.episode
        if self._step == 0:
            self._step = 1
            return {
                "type": "placements",
                "step": 1,
                "placements": [placement(current)],
                "dictionary": [module(current)],
            }
        self._step = 0
        self.episode += 1
        return {
            "type": "episodeDone",
            "completedEpisode": current,
            "nextEpisode": self.episode,
            "placements": [placement(current)],
            "dictionary": [module(current)],
            "metrics": {
                "score": str(SCORE_OFFSET + current),
                "rawScore": SCORE_OFFSET + current + 1,
                "fillRatio": 0.5,
                "rentableRatio": 0.75,
                "moduleCount": 1,
                "dictionaryLength": 1,
                "policyLoss": -0.125,
                "baseline": 0.4,
                "candidateEvaluations": 7,
                "topologyValid": True,
                "topologyViolations": [],
                "topologyViolationRate": 0.0,
                "topologyPenalty": 0.0,
                "bpeBonus": 3.0,
                "bpeRounds": 1,
                "reusedBpeModules": 1,
                "vocabSize": 2,
                "unmergedTriangles": 0,
                "averageUnmergedTriangles": 0.0,
                "unmergedTrianglePenalty": 0.0,
                "triangleRatio": 0.0,
                "performanceTimings": {
                    "candidateGeneration": {
                        "avg": 2.0,
                        "min": 1.0,
                        "max": 3.0,
                        "count": 2,
                    },
                    "learning": {
                        "avg": 4.0,
                        "min": 4.0,
                        "max": 4.0,
                        "count": 1,
                    },
                },
            },
        }
'''


class BenchmarkUnitTests(unittest.TestCase):
    def test_percentiles_and_numeric_summary(self):
        self.assertEqual(benchmark.percentile([1, 2, 3, 4], 0.5), 2.5)
        self.assertAlmostEqual(benchmark.percentile([1, 2, 3, 4], 0.95), 3.85)
        summary = benchmark.numeric_summary([1, None, "3", float("nan")])
        self.assertEqual(summary["count"], 2)
        self.assertEqual(summary["mean"], 2.0)

    def test_inline_settings_and_overrides(self):
        long_value = "x" * 5000
        settings = benchmark.parse_settings(
            json.dumps({"name": long_value, "parallelEnvironments": 4}),
            ["parallelEnvironments=8", "allowStop=true"],
        )
        self.assertEqual(settings["name"], long_value)
        self.assertEqual(settings["parallelEnvironments"], 8)
        self.assertTrue(settings["allowStop"])

    def test_layout_hash_canonicalizes_polygon_encoding(self):
        forward = [
            {"x": 0, "y": 0},
            {"x": 2, "y": 0},
            {"x": 2, "y": 1},
            {"x": 0, "y": 1},
        ]
        reversed_from_other_vertex = [forward[2], forward[1], forward[0], forward[3]]
        base = {"id": "p0", "instanceIdx": 0, "module": {"id": "m0"}}
        self.assertEqual(
            benchmark.layout_hash([{**base, "poly": forward}]),
            benchmark.layout_hash([{**base, "poly": reversed_from_other_vertex}]),
        )

    def test_profiler_aggregation_is_count_weighted(self):
        aggregate = {}
        benchmark._aggregate_profiler(
            aggregate,
            {"phase": {"avg": 2.0, "min": 1.0, "max": 3.0, "count": 2}},
        )
        benchmark._aggregate_profiler(
            aggregate,
            {"phase": {"avg": 5.0, "min": 4.0, "max": 6.0, "count": 1}},
        )
        phase = benchmark._finalize_profiler(aggregate)["phase"]
        self.assertEqual(phase["count"], 3)
        self.assertEqual(phase["meanMs"], 3.0)
        self.assertEqual(phase["minMs"], 1.0)
        self.assertEqual(phase["maxMs"], 6.0)


class BenchmarkIntegrationTests(unittest.TestCase):
    def _make_module(self, parent: Path, name: str, score_offset: int) -> Path:
        module_dir = parent / name
        module_dir.mkdir()
        (module_dir / "geometry.py").write_text("", encoding="utf-8")
        (module_dir / "graph.py").write_text("", encoding="utf-8")
        (module_dir / "server.py").write_text(
            textwrap.dedent(FAKE_SERVER).replace("__SCORE_OFFSET__", str(score_offset)),
            encoding="utf-8",
        )
        return module_dir

    def test_controller_isolates_modules_and_writes_complete_reports(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline = self._make_module(root, "baseline", 10)
            contender = self._make_module(root, "contender", 20)
            json_path = root / "report.json"
            csv_path = root / "episodes.csv"
            command = [
                sys.executable,
                str(BENCHMARK_PATH),
                "--module-dir",
                f"before={baseline}",
                "--module-dir",
                f"after={contender}",
                "--episodes",
                "2",
                "--warmup",
                "1",
                "--seed",
                "41",
                "--settings",
                '{"parallelEnvironments": 1}',
                "--max-steps",
                "4",
                "--episode-timeout",
                "5",
                "--run-timeout",
                "15",
                "--json-out",
                str(json_path),
                "--csv-out",
                str(csv_path),
                "--quiet",
            ]
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            report = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual([run["status"] for run in report["runs"]], ["complete", "complete"])
            self.assertEqual([run["episodesCompleted"] for run in report["runs"]], [2, 2])
            self.assertTrue(all(run["learningObserved"] for run in report["runs"]))
            self.assertEqual(report["runs"][0]["quality"]["candidateEvaluationsTotal"], 14)
            self.assertEqual(
                report["runs"][0]["profilerPhases"]["candidateGeneration"]["count"],
                4,
            )
            self.assertEqual(report["runs"][0]["quality"]["vocabSize"]["mean"], 2.0)
            self.assertIn("tracemallocPeakBytes", report["runs"][0]["memory"])
            self.assertEqual(report["runs"][0]["quality"]["score"]["mean"], 11.5)
            self.assertEqual(report["runs"][1]["quality"]["score"]["mean"], 21.5)

            comparison = report["comparisons"][0]
            self.assertEqual(comparison["pairedEpisodes"], 2)
            self.assertEqual(comparison["actionHashMatches"], 2)
            self.assertEqual(comparison["layoutHashMatches"], 2)
            self.assertEqual(comparison["meanScoreDelta"], 10.0)
            self.assertEqual(
                report["runs"][0]["determinism"]["actionSequenceHash"],
                report["runs"][1]["determinism"]["actionSequenceHash"],
            )

            with csv_path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 4)
            self.assertIn("stepP95Seconds", rows[0])
            self.assertIn("actionHash", rows[0])
            self.assertIn("triangleRatio", rows[0])


if __name__ == "__main__":
    unittest.main()
