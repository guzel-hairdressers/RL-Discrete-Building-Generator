from __future__ import annotations
import time
import torch
import random
import json
import os
import sys
import server

def run_750_episode_convergence_any():
    num_episodes = 750
    checkpoint_interval = 50
    
    # Exact training mode distribution: "Any size (procedural)" and procedural boundary types
    settings = dict(server.DEFAULT_SETTINGS)
    settings["siteAreaTier"] = "ANY"
    settings["boundaryType"] = "free"
    settings["parallelEnvironments"] = 4
    settings["maxModules"] = 120
    settings["seed"] = 42

    print("=" * 115, flush=True)
    print("750-EPISODE CONVERGENCE BENCHMARK (ANY SIZE PROCEDURAL & AUTO-CHANGE SITES)")
    print("Comparing: v0.8.4 (Phase 1G MLP Baseline) vs v0.8.5 (Phase 1H SE(2)-Equivariant Set Transformer)")
    print(f"Configuration: {num_episodes} Sequential PPO Episodes, Site Tier=ANY, Boundary=FREE, 4 Parallel Floors", flush=True)
    print("=" * 115, flush=True)

    results = {
        "v084_mlp": {"scores": [], "fills": [], "times": [], "rentables": [], "checkpoints": {}},
        "v085_se2": {"scores": [], "fills": [], "times": [], "rentables": [], "checkpoints": {}},
    }

    # -------------------------------------------------------------
    # 1. RUN v0.8.4 (MLP Policy Head)
    # -------------------------------------------------------------
    print("\n>>> [1/2] TRAINING v0.8.4 (Phase 1G MLP Baseline) FOR 750 EPISODES...", flush=True)
    torch.manual_seed(42)
    random.seed(42)
    trainer_mlp = server.ParallelTrainer(settings=settings)
    mlp_head = torch.nn.Sequential(
        torch.nn.Linear(server.PLACEMENT_FEATURE_DIM, 96),
        torch.nn.LayerNorm(96),
        torch.nn.SiLU(),
        torch.nn.Linear(96, 48),
        torch.nn.SiLU(),
        torch.nn.Linear(48, 1),
    )
    trainer_mlp.model.transformer.forward = lambda f, p=None, a=None: mlp_head(f).squeeze(-1)

    t0_mlp = time.perf_counter()
    for ep in range(1, num_episodes + 1):
        trainer_mlp.new_site()
        ep_t0 = time.perf_counter()
        while True:
            res = trainer_mlp.step(trainer_mlp.generation_id, trainer_mlp.episode)
            if res.get("type") == "episodeDone" or all(e.done for e in trainer_mlp.environments):
                break
        ep_duration = time.perf_counter() - ep_t0
        metrics = res.get("metrics", {})
        score = float(metrics.get("score", 0.0))
        fill = float(metrics.get("fillRatio", 0.0))
        rentable = float(metrics.get("rentableRatio", 0.0))

        results["v084_mlp"]["scores"].append(score)
        results["v084_mlp"]["fills"].append(fill)
        results["v084_mlp"]["times"].append(ep_duration)
        results["v084_mlp"]["rentables"].append(rentable)

        if ep % checkpoint_interval == 0 or ep in (1, 10, 25, 100, 250, 500, 750):
            recent_scores = results["v084_mlp"]["scores"][-50:]
            recent_fills = results["v084_mlp"]["fills"][-50:]
            avg_score = sum(recent_scores) / len(recent_scores)
            avg_fill = sum(recent_fills) / len(recent_fills)
            results["v084_mlp"]["checkpoints"][ep] = {
                "avgScore50": round(avg_score, 2),
                "avgFill50": round(avg_fill * 100.0, 1),
                "lastScore": round(score, 2),
                "lastFill": round(fill * 100.0, 1),
            }
            elapsed = time.perf_counter() - t0_mlp
            print(f" [v0.8.4 MLP] Ep {ep:03d}/{num_episodes} | AvgScore(50)={avg_score:5.2f} | AvgFill(50)={avg_fill*100:4.1f}% | EpTime={ep_duration:4.2f}s | Elapsed={elapsed/60:4.1f}m", flush=True)

    # -------------------------------------------------------------
    # 2. RUN v0.8.5 (SE(2)-Equivariant Relational Set Transformer)
    # -------------------------------------------------------------
    print("\n>>> [2/2] TRAINING v0.8.5 (Phase 1H SE(2) Set Transformer) FOR 750 EPISODES...", flush=True)
    torch.manual_seed(42)
    random.seed(42)
    trainer_se2 = server.ParallelTrainer(settings=settings)

    t0_se2 = time.perf_counter()
    for ep in range(1, num_episodes + 1):
        trainer_se2.new_site()
        ep_t0 = time.perf_counter()
        while True:
            res = trainer_se2.step(trainer_se2.generation_id, trainer_se2.episode)
            if res.get("type") == "episodeDone" or all(e.done for e in trainer_se2.environments):
                break
        ep_duration = time.perf_counter() - ep_t0
        metrics = res.get("metrics", {})
        score = float(metrics.get("score", 0.0))
        fill = float(metrics.get("fillRatio", 0.0))
        rentable = float(metrics.get("rentableRatio", 0.0))

        results["v085_se2"]["scores"].append(score)
        results["v085_se2"]["fills"].append(fill)
        results["v085_se2"]["times"].append(ep_duration)
        results["v085_se2"]["rentables"].append(rentable)

        if ep % checkpoint_interval == 0 or ep in (1, 10, 25, 100, 250, 500, 750):
            recent_scores = results["v085_se2"]["scores"][-50:]
            recent_fills = results["v085_se2"]["fills"][-50:]
            avg_score = sum(recent_scores) / len(recent_scores)
            avg_fill = sum(recent_fills) / len(recent_fills)
            results["v085_se2"]["checkpoints"][ep] = {
                "avgScore50": round(avg_score, 2),
                "avgFill50": round(avg_fill * 100.0, 1),
                "lastScore": round(score, 2),
                "lastFill": round(fill * 100.0, 1),
            }
            elapsed = time.perf_counter() - t0_se2
            print(f" [v0.8.5 SE2] Ep {ep:03d}/{num_episodes} | AvgScore(50)={avg_score:5.2f} | AvgFill(50)={avg_fill*100:4.1f}% | EpTime={ep_duration:4.2f}s | Elapsed={elapsed/60:4.1f}m", flush=True)

    # -------------------------------------------------------------
    # 3. SAVE RESULTS & PRINT CONVERGENCE TABLE
    # -------------------------------------------------------------
    with open("benchmarks/convergence_750_any_results.json", "w") as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 115, flush=True)
    print("750-EPISODE CONVERGENCE SUMMARY (ANY SIZE PROCEDURAL DISTRIBUTION)", flush=True)
    print("=" * 115, flush=True)
    print(f"{'Milestone':<15} | {'v0.8.4 MLP Score':<18} | {'v0.8.5 SE2 Score':<18} | {'v0.8.4 Fill':<14} | {'v0.8.5 Fill':<14} | {'Delta Score'}", flush=True)
    print("-" * 115, flush=True)
    for ckpt in (50, 100, 250, 500, 750):
        mlp_sc = results["v084_mlp"]["checkpoints"].get(ckpt, {}).get("avgScore50", 0.0)
        se2_sc = results["v085_se2"]["checkpoints"].get(ckpt, {}).get("avgScore50", 0.0)
        mlp_fl = results["v084_mlp"]["checkpoints"].get(ckpt, {}).get("avgFill50", 0.0)
        se2_fl = results["v085_se2"]["checkpoints"].get(ckpt, {}).get("avgFill50", 0.0)
        delta_sc = se2_sc - mlp_sc
        print(f"Episode {ckpt:<7} | {mlp_sc:15.2f} pts | {se2_sc:15.2f} pts | {mlp_fl:11.1f} % | {se2_fl:11.1f} % | {delta_sc:+10.2f} pts", flush=True)
    print("=" * 115, flush=True)

if __name__ == "__main__":
    run_750_episode_convergence_any()
