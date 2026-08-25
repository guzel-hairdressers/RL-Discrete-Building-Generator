"""Focused memory diagnostic: does current RSS plateau or grow unbounded?

Tracks psutil current RSS + the SE(2) native-buffer cache sizes across episodes
to attribute the plateau to ctypes-arena retention vs a true leak.

Usage: PYTHONPATH=src python3 benchmarks/diag_memory.py  [--episodes 60]
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import random

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

if os.environ.get("PYTHONHASHSEED") != "0":
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable, *sys.argv])

import psutil  # noqa: E402
import server  # noqa: E402
import geometry as G  # noqa: E402


def _cache_sizes() -> dict[str, int]:
    names = [
        "_packed_polygon_from_signature",
        "_packed_holes_from_signatures",
        "_native_shared_overlap_pair_from_signatures",
        "_packed_segments_from_signature",
        "_cached_enumerate_parametric_proposals",
    ]
    out = {}
    for name in names:
        fn = getattr(G, name, None)
        if fn is None or not hasattr(fn, "cache_info"):
            out[name] = -1
            continue
        info = fn.cache_info()
        out[name] = (info.currsize, info.maxsize)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=60)
    args = parser.parse_args()

    settings = dict(server.DEFAULT_SETTINGS)
    settings["siteAreaTier"] = "ANY"
    settings["boundaryType"] = "mixed"
    settings["parallelEnvironments"] = 4
    settings["maxModules"] = 120
    settings["seed"] = 42
    settings["learningRate"] = 0.001

    torch = server.torch
    torch.manual_seed(settings["seed"])
    random.seed(settings["seed"])
    trainer = server.ParallelTrainer(settings=settings)
    proc = psutil.Process()

    print("ep | rss_mb  peak_mb | poly buf holes ovl_pk segs | candidates/step | vocab")
    for ep in range(1, args.episodes + 1):
        trainer.new_site()
        total_cands = 0
        steps = 0
        while True:
            res = trainer.step(trainer.generation_id, trainer.episode)
            steps += 1
            total_cands += int(getattr(trainer, "last_candidate_evaluations", 0) or 0)
            if res.get("type") == "episodeDone":
                break
        rss = proc.memory_info().rss / (1024.0 * 1024.0)
        caches = _cache_sizes()
        poly = caches["_packed_polygon_from_signature"]
        holes = caches["_packed_holes_from_signatures"]
        ovl = caches["_native_shared_overlap_pair_from_signatures"]
        segs = caches["_packed_segments_from_signature"]
        cur_size = poly[0]
        vocab = len(trainer.dictionary)
        # Low-frequency print every 5 episodes + around the 50-ep clear.
        if ep % 5 == 0 or ep % 50 == 0:
            print(
                f"{ep:3d} | {rss:6.1f} | {poly[0]:4d}/{poly[1]} {holes[0]:4d}/{holes[1]} "
                f"{ovl[0]:5d}/{ovl[1]} {segs[0]:4d}/{segs[1]} | {total_cands:6d}/{steps:3d} | {vocab}",
                flush=True,
            )


if __name__ == "__main__":
    main()
