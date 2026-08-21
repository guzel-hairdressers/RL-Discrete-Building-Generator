"""500-Episode Head-to-Head Convergence Benchmark: v0.8.5 vs v0.8.6-a vs v0.8.6-b.

Tests learning convergence across 500 episodes under standard user settings:
- Site Area Tier: "ANY"
- Boundary: "FREE"
- Auto-changing procedural sites
- 4 Parallel Floors
- Max Modules: 100
"""

from __future__ import annotations
import time
import torch
import random
import json
import os
import sys
import math
import importlib.util

def _load_branch_module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

def run_convergence_comparison(num_episodes: int = 500):
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    scratch_branches = os.path.join(repo_root, "scratch", "branches")
    os.makedirs(scratch_branches, exist_ok=True)

    # Ensure branch files exist
    import subprocess
    for branch, fname in [("main", "server_v085.py"), ("version/v0.8.6-a", "server_v086a.py"), ("version/v0.8.6-b", "server_v086b.py")]:
        fpath = os.path.join(scratch_branches, fname)
        if not os.path.exists(fpath):
            subprocess.run(f"git show {branch}:src/server.py > '{fpath}'", shell=True, check=True)

    mod_v085 = _load_branch_module("server_v085", os.path.join(scratch_branches, "server_v085.py"))
    mod_v086a = _load_branch_module("server_v086a", os.path.join(scratch_branches, "server_v086a.py"))
    mod_v086b = _load_branch_module("server_v086b", os.path.join(scratch_branches, "server_v086b.py"))

    settings = dict(mod_v085.DEFAULT_SETTINGS)
    settings["siteAreaTier"] = "ANY"
    settings["boundaryType"] = "free"
    settings["parallelEnvironments"] = 4
    settings["maxModules"] = 100
    settings["seed"] = 42

    print("=" * 115, flush=True)
    print(f"500-EPISODE DUAL CONVERGENCE BENCHMARK (ANY SIZE PROCEDURAL & AUTO-CHANGE SITES)")
    print(f"Comparing: v0.8.5 Baseline vs v0.8.6-a (Dynamic Critic GAE) vs v0.8.6-b (Rollout Buffer PPO)")
    print(f"Configuration: {num_episodes} Episodes, Site Tier=ANY, Boundary=FREE, 4 Parallel Floors", flush=True)
    print("=" * 115, flush=True)

    results = {
        "v085_baseline": {"scores": [], "fills": [], "times": [], "rentables": [], "modules": []},
        "v086a_dynamic_critic": {"scores": [], "fills": [], "times": [], "rentables": [], "modules": []},
        "v086b_rollout_buffer": {"scores": [], "fills": [], "times": [], "rentables": [], "modules": []},
    }

    variants = [
        ("v085_baseline", "v0.8.5 Baseline (Fixed Reward, Static Site Critic)", mod_v085, 1),
        ("v086a_dynamic_critic", "v0.8.6-a (Dynamic Set Transformer Critic + GAE)", mod_v086a, 1),
        ("v086b_rollout_buffer", "v0.8.6-b (Multi-Episode Rollout Buffer PPO)", mod_v086b, 4),
    ]

    for var_key, var_name, branch_mod, buf_eps in variants:
        print(f"\n>>> TRAINING {var_name} FOR {num_episodes} EPISODES...", flush=True)
        var_settings = dict(branch_mod.DEFAULT_SETTINGS)
        var_settings["siteAreaTier"] = "ANY"
        var_settings["boundaryType"] = "free"
        var_settings["parallelEnvironments"] = 4
        var_settings["maxModules"] = 100
        var_settings["seed"] = 42
        if "bufferEpisodes" in branch_mod.DEFAULT_SETTINGS:
            var_settings["bufferEpisodes"] = buf_eps

        torch.manual_seed(42)
        random.seed(42)
        trainer = branch_mod.ParallelTrainer(settings=var_settings)

        t0 = time.perf_counter()
        for ep in range(1, num_episodes + 1):
            trainer.new_site()
            ep_t0 = time.perf_counter()
            while True:
                res = trainer.step(trainer.generation_id, trainer.episode)
                if res.get("type") == "episodeDone" or all(e.done for e in trainer.environments):
                    break
            ep_time = time.perf_counter() - ep_t0
            m = res.get("metrics", {})
            score = float(m.get("score", 0.0))
            fill = float(m.get("fillRatio", 0.0))
            rentable = float(m.get("rentableRatio", 0.0))
            module_count = int(m.get("moduleCount", 0))

            results[var_key]["scores"].append(score)
            results[var_key]["fills"].append(fill)
            results[var_key]["times"].append(ep_time)
            results[var_key]["rentables"].append(rentable)
            results[var_key]["modules"].append(module_count)

            if ep % 50 == 0 or ep in (1, 10, 25):
                recent_scores = results[var_key]["scores"][-50:]
                recent_fills = results[var_key]["fills"][-50:]
                avg_score = sum(recent_scores) / len(recent_scores)
                avg_fill = sum(recent_fills) / len(recent_fills)
                print(
                    f"  [{var_key}] Ep {ep:03d}/{num_episodes} | AvgScore(50): {avg_score:5.2f} | "
                    f"AvgFill(50): {avg_fill*100:4.1f}% | LastScore: {score:5.2f} | Time: {time.perf_counter()-t0:5.1f}s",
                    flush=True
                )

        total_time = time.perf_counter() - t0
        first_50_s = sum(results[var_key]["scores"][:50]) / 50.0
        last_50_s = sum(results[var_key]["scores"][-50:]) / 50.0
        print(f">>> {var_name} COMPLETED in {total_time/60:.2f}m. Score Delta: {first_50_s:.2f} -> {last_50_s:.2f} (+{last_50_s-first_50_s:+.2f} pts)\n")

    # Save output JSON
    out_path = os.path.join(os.path.dirname(__file__), "convergence_500_results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to {out_path}")

    # Print comparative summary table
    print("\n" + "=" * 115)
    print("FINAL HEAD-TO-HEAD COMPARATIVE SUMMARY (500 EPISODES)")
    print("=" * 115)
    print(f"{'Variant':<32} | {'Initial (Ep 1-50)':<18} | {'Mid (Ep 225-275)':<18} | {'Final (Ep 450-500)':<18} | {'Improvement':<12}")
    print("-" * 115)
    for var_key, var_name, _, _ in variants:
        scores = results[var_key]["scores"]
        init_avg = sum(scores[:50]) / 50.0
        mid_avg = sum(scores[225:275]) / 50.0
        final_avg = sum(scores[-50:]) / 50.0
        delta = final_avg - init_avg
        print(f"{var_name:<32} | {init_avg:18.2f} | {mid_avg:18.2f} | {final_avg:18.2f} | {delta:+11.2f}")
    print("=" * 115)

if __name__ == "__main__":
    run_convergence_comparison(500)
