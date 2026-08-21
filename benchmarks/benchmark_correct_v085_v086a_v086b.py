"""500-Episode Correct Head-to-Head Convergence Benchmark: v0.8.5 vs v0.8.6-a vs v0.8.6-b.

Properly isolates each branch's server.py via importlib and verifies divergence.
"""

from __future__ import annotations
import sys, os, time, json, random, importlib.util
import torch

def load_branch(name: str, path: str):
    """Load a branch's server.py as an isolated module."""
    src_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

def run_variant(mod, var_name: str, num_episodes: int, seed: int = 42) -> dict:
    """Run one variant for N episodes, return metrics."""
    torch.manual_seed(seed)
    random.seed(seed)

    settings = dict(mod.DEFAULT_SETTINGS)
    settings["siteAreaTier"] = "ANY"
    settings["boundaryType"] = "free"
    settings["parallelEnvironments"] = 4
    settings["seed"] = seed

    trainer = mod.ParallelTrainer(settings=settings)
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
            print(
                f"  [{var_name}] Ep {ep:03d}/{num_episodes} | "
                f"Avg50: {avg:5.2f} | Fill: {avg_fill*100:4.1f}% | "
                f"Mods: {avg_mods:4.1f} | Elapsed: {elapsed/60:.1f}m",
                flush=True,
            )

    total = time.perf_counter() - t0
    return {
        "scores": scores,
        "fills": fills,
        "times": times,
        "modules": modules,
        "total_seconds": round(total, 2),
    }


if __name__ == "__main__":
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    branches_dir = os.path.join(repo, "scratch", "branches")

    variants = [
        ("v085_baseline", "server_v085", os.path.join(branches_dir, "server_v085.py")),
        ("v086a_dynamic_critic", "server_v086a", os.path.join(branches_dir, "server_v086a.py")),
        ("v086b_rollout_buffer", "server_v086b", os.path.join(branches_dir, "server_v086b.py")),
    ]

    # Sanity check: verify files exist and are different
    hashes = []
    for _, _, path in variants:
        if not os.path.exists(path):
            print(f"FATAL: {path} does not exist. Extract branch modules first.", flush=True)
            sys.exit(1)
        import hashlib
        with open(path, "rb") as f:
            hashes.append(hashlib.md5(f.read()).hexdigest())
    if len(set(hashes)) != 3:
        print(f"FATAL: Branch modules are not all unique! MD5s: {hashes}", flush=True)
        sys.exit(1)
    print(f"✓ All 3 branch modules verified unique (MD5s differ)", flush=True)

    num_episodes = 500
    print("=" * 100, flush=True)
    print(f"500-EPISODE CONVERGENCE BENCHMARK (CORRECT BRANCH ISOLATION)")
    print(f"v0.8.5 Baseline vs v0.8.6-a (Dynamic Critic GAE) vs v0.8.6-b (Rollout Buffer PPO)")
    print(f"Settings: {num_episodes} eps, ANY sites, FREE boundary, 4 parallel floors", flush=True)
    print("=" * 100, flush=True)

    results = {}
    for var_key, mod_name, mod_path in variants:
        print(f"\n>>> Running {var_key}...", flush=True)
        mod = load_branch(mod_name, mod_path)
        results[var_key] = run_variant(mod, var_key, num_episodes)

        # Early divergence check after second variant
        if len(results) >= 2:
            keys = list(results.keys())
            s1 = results[keys[-2]]["scores"][:20]
            s2 = results[keys[-1]]["scores"][:20]
            if s1 == s2:
                print(
                    "!!! WARNING: First 20 scores are IDENTICAL between "
                    f"{keys[-2]} and {keys[-1]}. "
                    "Benchmark may be running the same code twice!",
                    flush=True,
                )
            else:
                diff = sum(abs(a - b) for a, b in zip(s1, s2))
                print(
                    f"    ✓ Divergence check passed: L1 diff over first 20 eps = "
                    f"{diff:.4f}",
                    flush=True,
                )

    # Save
    out_path = os.path.join(repo, "benchmarks", "convergence_500_correct.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {out_path}", flush=True)

    # Summary table
    print("\n" + "=" * 100)
    print("CONVERGENCE SUMMARY (500 EPISODES)")
    print("=" * 100)
    print(
        f"{'Variant':30s} | {'First50':>8s} | {'Mid50':>8s} | {'Last50':>8s} | "
        f"{'Delta':>8s} | {'AvgFill':>8s} | {'AvgMods':>8s} | {'Time':>6s}"
    )
    print("-" * 100)
    for var_key in results:
        s = results[var_key]["scores"]
        f = results[var_key]["fills"]
        m = results[var_key]["modules"]
        first50 = sum(s[:50]) / 50
        mid50 = sum(s[225:275]) / 50
        last50 = sum(s[-50:]) / 50
        delta = last50 - first50
        avg_fill = sum(f) / len(f) * 100
        avg_mods = sum(m) / len(m)
        total_min = results[var_key]["total_seconds"] / 60
        print(
            f"{var_key:30s} | {first50:8.2f} | {mid50:8.2f} | {last50:8.2f} | "
            f"{delta:+8.2f} | {avg_fill:7.1f}% | {avg_mods:8.1f} | {total_min:5.1f}m"
        )
    print("=" * 100)
