#!/usr/bin/env python3
"""500-Episode Multi-Buffer Benchmark: Buffer=1 vs Buffer=4 vs Buffer=8 Episodes.

Evaluates throughput latency, score convergence, and fill ratio under the new
Distance-to-Air continuous daylight metric across procedural auto-changing sites.
"""

import json
import os
import random
import sys
import time
import torch

# Add src to path
sys.path.insert(0, os.path.abspath('src'))
import server

def run_buffer_benchmark(buffer_episodes: int, num_episodes: int = 500, seed: int = 42) -> dict:
    print("=" * 80)
    print(f"RUNNING BUFFER = {buffer_episodes} EPISODE(S) BENCHMARK ({num_episodes} Episodes, Seed={seed})")
    print("=" * 80)

    torch.manual_seed(seed)
    random.seed(seed)

    settings = dict(server.DEFAULT_SETTINGS)
    settings["siteAreaTier"] = "ANY"
    settings["boundaryType"] = "free"
    settings["parallelEnvironments"] = 4
    settings["seed"] = seed
    settings["bufferEpisodes"] = buffer_episodes
    settings["learningRate"] = 0.003

    trainer = server.ParallelTrainer(settings=settings)
    scores, fills, times, modules = [], [], [], []

    t0 = time.perf_counter()

    for ep in range(1, num_episodes + 1):
        trainer.new_site()
        ep_t0 = time.perf_counter()
        while True:
            res = trainer.step(trainer.generation_id, trainer.episode)
            if res.get("type") == "episodeDone":
                break
        ep_time = time.perf_counter() - ep_t0
        m = res.get("metrics", {})
        s = float(m.get("score", 0.0))
        f = float(m.get("fillRatio", 0.0))
        mc = int(m.get("moduleCount", 0))
        scores.append(s)
        fills.append(f)
        times.append(ep_time)
        modules.append(mc)

        if ep % 50 == 0 or ep in (1, 10, 20):
            recent = scores[-50:]
            avg = sum(recent) / len(recent)
            avg_fill = sum(fills[-50:]) / len(fills[-50:])
            avg_mods = sum(modules[-50:]) / len(modules[-50:])
            elapsed = time.perf_counter() - t0
            ms_per_ep = (elapsed / ep) * 1000.0
            print(
                f"[Buffer={buffer_episodes}ep] Ep {ep:3d}/500: Last50 Score={avg:6.2f} pts | "
                f"Fill={avg_fill*100:4.1f}% | Mods={avg_mods:4.1f} | "
                f"Speed={ms_per_ep:5.1f} ms/ep | {elapsed/60:4.1f}m"
            )

    total_time = time.perf_counter() - t0
    return {
        "buffer_episodes": buffer_episodes,
        "scores": scores,
        "fills": fills,
        "times": times,
        "modules": modules,
        "total_seconds": total_time,
    }

def main():
    num_episodes = 500
    results = {}

    for buf in [1, 4, 8]:
        res = run_buffer_benchmark(buf, num_episodes=num_episodes, seed=42)
        results[f"buffer_{buf}_episodes"] = res

    out_file = "benchmarks/buffer_scaling_1_4_8_results.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)

    print("=" * 80)
    print(f"ALL BUFFER BENCHMARKS COMPLETE! Results saved to {out_file}")
    print("=" * 80)

if __name__ == "__main__":
    main()
