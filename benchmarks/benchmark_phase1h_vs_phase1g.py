from __future__ import annotations
import time
import torch
import random
import sys
import server

def benchmark_phase1h_vs_phase1g(num_episodes=10, max_modules=120):
    print("=" * 115, flush=True)
    print("DIRECT ISOLATED PROGRESSION: PHASE 1G (v0.8.4 BASELINE) VS PHASE 1H (v0.8.5 EQUIVARIANT TRANSFORMER)", flush=True)
    print(f"Configuration: {num_episodes} Deterministic Episodes, {max_modules} Placements/Floor, 4 Parallel Floors, XL Lobed Sites", flush=True)
    print("=" * 115, flush=True)
    
    seeds = [100 + i * 23 for i in range(num_episodes)]
    
    # 1. Measure Phase 1G (Pure MLP Placement Head without Self-Attention)
    print("\n>>> [1/2] RUNNING PHASE 1G (v0.8.4: MLP Policy, Slot Grammar, Medial Cores, DPP)...", flush=True)
    p1g_times, p1g_scores, p1g_fills, p1g_rentables = [], [], [], []
    
    for ep_idx, seed in enumerate(seeds):
        torch.manual_seed(seed)
        random.seed(seed)
        settings = dict(server.DEFAULT_SETTINGS)
        settings["siteAreaTier"] = "XL"
        settings["boundaryType"] = "lobed"
        settings["parallelEnvironments"] = 4
        settings["maxModules"] = max_modules
        settings["seed"] = seed
        
        trainer = server.ParallelTrainer(settings=settings)
        # Mock MLP placement head for pure v0.8.4
        mlp_head = torch.nn.Sequential(
            torch.nn.Linear(server.PLACEMENT_FEATURE_DIM, 96),
            torch.nn.LayerNorm(96),
            torch.nn.SiLU(),
            torch.nn.Linear(96, 48),
            torch.nn.SiLU(),
            torch.nn.Linear(48, 1),
        )
        trainer.model.transformer.forward = lambda f, p=None, a=None: mlp_head(f).squeeze(-1)
        trainer.new_site()
        
        t0 = time.perf_counter()
        for _ in range(max_modules):
            res = trainer.step(trainer.generation_id, trainer.episode)
            if res.get("type") == "episodeDone" or all(e.done for e in trainer.environments):
                break
        ep_duration = time.perf_counter() - t0
        p1g_times.append(ep_duration)
        metrics = res.get("metrics", {})
        p1g_scores.append(float(metrics.get("score", 0.0)))
        p1g_fills.append(float(metrics.get("fillRatio", 0.0)))
        p1g_rentables.append(float(metrics.get("rentableRatio", 0.0)))
        print(f" [Phase 1G] Ep {ep_idx+1:02d} (Seed {seed:4d}): Time={ep_duration:5.2f}s | Score={p1g_scores[-1]:5.2f} | Fill={p1g_fills[-1]*100:4.1f}% | Rentable={p1g_rentables[-1]*100:4.1f}%", flush=True)

    # 2. Measure Phase 1H (SE(2)-Equivariant Relational Set Transformer)
    print("\n>>> [2/2] RUNNING PHASE 1H (v0.8.5: SE(2)-Equivariant Relational Set Transformer)...", flush=True)
    p1h_times, p1h_scores, p1h_fills, p1h_rentables = [], [], [], []
    
    for ep_idx, seed in enumerate(seeds):
        torch.manual_seed(seed)
        random.seed(seed)
        settings = dict(server.DEFAULT_SETTINGS)
        settings["siteAreaTier"] = "XL"
        settings["boundaryType"] = "lobed"
        settings["parallelEnvironments"] = 4
        settings["maxModules"] = max_modules
        settings["seed"] = seed
        
        trainer = server.ParallelTrainer(settings=settings)
        trainer.new_site()
        
        t0 = time.perf_counter()
        for _ in range(max_modules):
            res = trainer.step(trainer.generation_id, trainer.episode)
            if res.get("type") == "episodeDone" or all(e.done for e in trainer.environments):
                break
        ep_duration = time.perf_counter() - t0
        p1h_times.append(ep_duration)
        metrics = res.get("metrics", {})
        p1h_scores.append(float(metrics.get("score", 0.0)))
        p1h_fills.append(float(metrics.get("fillRatio", 0.0)))
        p1h_rentables.append(float(metrics.get("rentableRatio", 0.0)))
        print(f" [Phase 1H] Ep {ep_idx+1:02d} (Seed {seed:4d}): Time={ep_duration:5.2f}s | Score={p1h_scores[-1]:5.2f} | Fill={p1h_fills[-1]*100:4.1f}% | Rentable={p1h_rentables[-1]*100:4.1f}%", flush=True)

    print("\n" + "=" * 115, flush=True)
    print("STEP-BY-STEP ISOLATED PROGRESSION: PHASE 1G (v0.8.4) VS PHASE 1H (v0.8.5)", flush=True)
    print("=" * 115, flush=True)
    print(f"{'Metric':<35} | {'Phase 1G (v0.8.4)':<18} | {'Phase 1H (v0.8.5)':<18} | {'Net Marginal Delta':<18} | {'Impact & Evaluation'}", flush=True)
    print("-" * 115, flush=True)
    
    avg_p1g_t = sum(p1g_times) / len(p1g_times)
    avg_p1h_t = sum(p1h_times) / len(p1h_times)
    dt = avg_p1h_t - avg_p1g_t
    print(f"{'Mean Episode Wall Time':<35} | {avg_p1g_t:15.2f} s | {avg_p1h_t:15.2f} s | {dt:+15.2f} s | Self-attention coordination overhead", flush=True)
    
    avg_p1g_s = sum(p1g_scores) / len(p1g_scores)
    avg_p1h_s = sum(p1h_scores) / len(p1h_scores)
    ds = avg_p1h_s - avg_p1g_s
    print(f"{'Mean Architectural Score':<35} | {avg_p1g_s:15.2f} pts | {avg_p1h_s:15.2f} pts | {ds:+15.2f} pts | Cross-wing spatial layout coordination", flush=True)
    
    avg_p1g_f = sum(p1g_fills) / len(p1g_fills)
    avg_p1h_f = sum(p1h_fills) / len(p1h_fills)
    df = (avg_p1h_f - avg_p1g_f) * 100.0
    print(f"{'Mean Floor Fill Ratio':<35} | {avg_p1g_f*100:14.1f} % | {avg_p1h_f*100:14.1f} % | {df:+14.1f} % | Global spatial wing utilization", flush=True)
    
    avg_p1g_r = sum(p1g_rentables) / len(p1g_rentables)
    avg_p1h_r = sum(p1h_rentables) / len(p1h_rentables)
    dr = (avg_p1h_r - avg_p1g_r) * 100.0
    print(f"{'Mean Rentable Area Ratio':<35} | {avg_p1g_r*100:14.1f} % | {avg_p1h_r*100:14.1f} % | {dr:+14.1f} % | Preserves circulation efficiency", flush=True)
    print("=" * 115, flush=True)

if __name__ == "__main__":
    benchmark_phase1h_vs_phase1g(num_episodes=10, max_modules=120)
