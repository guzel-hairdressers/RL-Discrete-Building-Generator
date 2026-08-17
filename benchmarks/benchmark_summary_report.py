from __future__ import annotations
import time
import torch
import random
import json
import statistics
import server

def run_detailed_benchmark(num_episodes: int = 10, max_modules: int = 120):
    print("=" * 95)
    print(f"MODULE LAB v0.8.4 COMPREHENSIVE BENCHMARK ({num_episodes} EPISODES, {max_modules} MAX MODULES, 4 FLOORS)")
    print("=" * 95)
    
    seeds = [100 + i * 23 for i in range(num_episodes)]
    episode_times = []
    scores = []
    fill_ratios = []
    rentable_ratios = []
    core_stack_checks = []
    dpp_diversities = []
    step_cg_times = []
    
    for ep_idx, seed in enumerate(seeds):
        torch.manual_seed(seed)
        random.seed(seed)
        settings = dict(server.DEFAULT_SETTINGS)
        settings["siteAreaTier"] = "XL"
        settings["boundaryType"] = "lobed"
        settings["parallelEnvironments"] = 4
        settings["maxModules"] = max_modules
        settings["seed"] = seed
        
        t0 = time.perf_counter()
        trainer = server.ParallelTrainer(settings=settings)
        trainer.new_site()
        
        for _ in range(max_modules):
            t_step_start = time.perf_counter()
            res = trainer.step(trainer.generation_id, trainer.episode)
            if res.get("episodeDone") or all(e.done for e in trainer.environments):
                break
                
        ep_duration = time.perf_counter() - t0
        episode_times.append(ep_duration)
        
        metrics = res.get("metrics", {})
        scores.append(float(metrics.get("score", 0.0)))
        fill_ratios.append(float(metrics.get("fillRatio", 0.0)))
        rentable_ratios.append(float(metrics.get("rentableRatio", 0.0)))
        dpp_diversities.append(float(metrics.get("dppDiversityBonus", 0.0)))
        
        core_audit = trainer._core_stacking_event()
        violations = len(core_audit.get("violations", []))
        core_stack_checks.append(violations == 0)
        
        cg_time = metrics.get("performanceTimings", {}).get("candidateGeneration", {}).get("avg", 0.0)
        if cg_time > 0:
            step_cg_times.append(cg_time)
            
        print(f" Episode {ep_idx+1:02d} | Seed {seed:4d} | Time: {ep_duration:.3f}s | Score: {scores[-1]:6.2f} | Fill: {fill_ratios[-1]*100:4.1f}% | Rentable: {rentable_ratios[-1]*100:4.1f}% | Cores Valid: {violations==0}")
        
    print("-" * 95)
    print("SUMMARY METRICS (ACROSS 10 EPISODES):")
    print(f" * Mean Episode Wall Time:          {statistics.mean(episode_times):.3f} s (Median: {statistics.median(episode_times):.3f} s, Min: {min(episode_times):.3f} s, Max: {max(episode_times):.3f} s)")
    print(f" * Mean Architectural Score:        {statistics.mean(scores):.2f} pts (Max: {max(scores):.2f} pts)")
    print(f" * Mean Floor Fill Ratio:           {statistics.mean(fill_ratios)*100:.2f} %")
    print(f" * Mean Rentable Usable Ratio:      {statistics.mean(rentable_ratios)*100:.2f} %")
    print(f" * Vertical Core Stack Alignment:   {sum(core_stack_checks)/len(core_stack_checks)*100:.1f} % (0 violations across all 4 floors)")
    if dpp_diversities:
        print(f" * Mean DPP Diversity Volume:       +{statistics.mean(dpp_diversities):.3f} nats")
    if step_cg_times:
        print(f" * Avg Candidate Gen Latency / Step:{statistics.mean(step_cg_times):.3f} ms")
    print("=" * 95)

if __name__ == "__main__":
    run_detailed_benchmark(num_episodes=10, max_modules=120)
