from __future__ import annotations
import time
import torch
import random
import json
import server

def breakdown_episode_timing(seed=100, max_modules=120):
    print("=" * 95)
    print(f"EXACT PER-COMPONENT TIME BREAKDOWN (SEED {seed}, {max_modules} MODULES/FLOOR, 4 FLOORS)")
    print("=" * 95)
    
    torch.manual_seed(seed)
    random.seed(seed)
    settings = dict(server.DEFAULT_SETTINGS)
    settings["siteAreaTier"] = "XL"
    settings["boundaryType"] = "lobed"
    settings["parallelEnvironments"] = 4
    settings["maxModules"] = max_modules
    settings["seed"] = seed

    t_start = time.perf_counter()
    trainer = server.ParallelTrainer(settings=settings)
    trainer.new_site()
    
    step_count = 0
    for s in range(max_modules):
        step_count += 1
        res = trainer.step(trainer.generation_id, trainer.episode)
        if res.get("episodeDone") or all(e.done for e in trainer.environments):
            break
            
    total_time = time.perf_counter() - t_start
    metrics = res.get("metrics", {})
    timings = metrics.get("performanceTimings", {})
    
    print(f"Total Episode Wall Time: {total_time:.3f} s (Total Steps Taken: {step_count})")
    print("-" * 95)
    print(f"{'Subsystem / Operation':<35} | {'Total Time (ms)':<18} | {'% of Total Time':<18}")
    print("-" * 95)
    
    # Extract profiler values
    cg_total = timings.get("candidateGeneration", {}).get("avg", 0.0) * timings.get("candidateGeneration", {}).get("count", 0)
    bpe_total = timings.get("episodeBpeMerge", {}).get("avg", 0.0) * timings.get("episodeBpeMerge", {}).get("count", 0)
    term_total = timings.get("terminalMetrics", {}).get("avg", 0.0) * timings.get("terminalMetrics", {}).get("count", 0)
    learn_total = timings.get("learning", {}).get("avg", 0.0) * timings.get("learning", {}).get("count", 0)
    place_total = timings.get("placement", {}).get("avg", 0.0) * timings.get("placement", {}).get("count", 0)
    pol_total = timings.get("policyInference", {}).get("avg", 0.0) * timings.get("policyInference", {}).get("count", 0)
    dict_total = timings.get("dictSynthesis", {}).get("avg", 0.0) * timings.get("dictSynthesis", {}).get("count", 0)
    
    tot_ms = total_time * 1000.0
    items = [
        ("Candidate Generation (Geometry)", cg_total),
        ("BPE Graph Merge (End of Episode)", bpe_total),
        ("Terminal Metrics (Daylight / Areas)", term_total),
        ("PPO Learning & Backprop (PyTorch)", learn_total),
        ("Placement & State Update", place_total),
        ("Policy Inference (Forward Pass)", pol_total),
        ("Dictionary Synthesis", dict_total),
    ]
    
    accounted_ms = 0.0
    for name, dur_ms in items:
        pct = (dur_ms / tot_ms) * 100.0 if tot_ms > 0 else 0.0
        accounted_ms += dur_ms
        print(f"{name:<35} | {dur_ms:15.2f} ms | {pct:15.1f} %")
        
    other_ms = max(0.0, tot_ms - accounted_ms)
    print(f"{'WebSocket / Formatting / Other':<35} | {other_ms:15.2f} ms | {(other_ms/tot_ms)*100.0:15.1f} %")
    print("=" * 95)

if __name__ == "__main__":
    breakdown_episode_timing(seed=100, max_modules=120)
