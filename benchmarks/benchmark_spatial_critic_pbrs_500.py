#!/usr/bin/env python3
"""500-Episode Convergence Benchmark: SE(2) Spatial Critic + PBRS + Continuous Distance-to-Air.

Evaluates learning progression, fill ratio, and throughput latency under procedural
auto-changing parcels (siteAreaTier: 'ANY', boundaryType: 'free', 4 stories, seed=42).
"""

import json
import os
import random
import sys
import time
import torch

sys.path.insert(0, os.path.abspath('src'))
import server

def main():
    print("=" * 80)
    print("STARTING 500-EPISODE BENCHMARK: SE(2) SPATIAL CRITIC + PBRS (Seed=42)")
    print("=" * 80)

    num_episodes = 500
    seed = 42

    torch.manual_seed(seed)
    random.seed(seed)

    settings = dict(server.DEFAULT_SETTINGS)
    settings["siteAreaTier"] = "ANY"
    settings["boundaryType"] = "free"
    settings["parallelEnvironments"] = 4
    settings["seed"] = seed
    settings["bufferEpisodes"] = 1
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
                f"[SpatialCritic+PBRS] Ep {ep:3d}/500: Last50 Score={avg:6.2f} pts | "
                f"Fill={avg_fill*100:4.1f}% | Mods={avg_mods:4.1f} | "
                f"Cur={s:6.2f} pts (fill={f*100:4.1f}%, mods={mc:2d}) | "
                f"Speed={ms_per_ep:5.1f} ms/ep | {elapsed/60:4.1f}m"
            )

    total_time = time.perf_counter() - t0
    res_dict = {
        "scores": scores,
        "fills": fills,
        "times": times,
        "modules": modules,
        "total_seconds": total_time,
    }

    out_file = "benchmarks/convergence_spatial_critic_pbrs_500.json"
    with open(out_file, "w") as f:
        json.dump(res_dict, f, indent=2)

    print("=" * 80)
    print(f"BENCHMARK COMPLETE ({total_time/60:.2f} min)")
    first50 = sum(scores[:50]) / 50.0
    mid50 = sum(scores[225:275]) / 50.0
    last50 = sum(scores[-50:]) / 50.0
    delta = last50 - first50
    avg_fill = sum(fills) / len(fills)
    avg_mods = sum(modules) / len(modules)
    print(f"First 50: {first50:.2f} pts | Mid 50: {mid50:.2f} pts | Last 50: {last50:.2f} pts | Delta: {delta:+.2f} pts")
    print(f"Avg Fill: {avg_fill*100:.1f}% | Avg Modules: {avg_mods:.1f}")
    print(f"Results saved to {out_file}")

if __name__ == "__main__":
    main()
