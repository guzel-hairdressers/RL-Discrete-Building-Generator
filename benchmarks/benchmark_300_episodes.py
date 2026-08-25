"""300-episode convergence / speed / memory benchmark.

Runs the CURRENT working-tree trainer (whatever `src/server.py` is at this
commit) for a fixed number of episodes under a fixed, reproducible config, and
records per-episode metrics + wall-clock time + peak RSS so that successive
code changes (snapshot-timing fix, mixed-in-value fix, A2C reframe) can be
compared apples-to-apples against the same baseline.

Usage:
    PYTHONPATH=src python3 benchmarks/benchmark_300_episodes.py --label baseline --episodes 300
    PYTHONPATH=src python3 benchmarks/benchmark_300_episodes.py --label fix_snapshot --episodes 300
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import statistics
import sys
import time
import random

import torch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

# Reproducibility: Python randomizes string hashing per process (PYTHONHASHSEED),
# which changes the iteration order of the trainer's string-keyed sets (candidate
# dedup, adjacency, core_ids) and yields divergent trajectories despite identical
# RNG seeds. Pin it by re-execing once with the variable set.
if os.environ.get("PYTHONHASHSEED") != "0":
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable, *sys.argv])

import server  # noqa: E402


def peak_rss_mb() -> float:
    """Peak resident set size of this process, in MB."""
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # ru_maxrss is bytes on macOS, KiB on Linux.
    if sys.platform == "darwin":
        return raw / (1024.0 * 1024.0)
    return raw / 1024.0


def default_settings() -> dict:
    settings = dict(server.DEFAULT_SETTINGS)
    # Quality-benchmark protocol: ANY tier, MIXED boundary (procedural + real
    # sites), auto-changing sites. Multi-floor path stays enabled.
    settings["siteAreaTier"] = "ANY"
    settings["boundaryType"] = "mixed"
    settings["parallelEnvironments"] = 4
    settings["maxModules"] = 120
    settings["seed"] = 42
    return settings


def _safe_get(metrics: dict, *keys, default=0.0) -> float:
    for key in keys:
        if key in metrics:
            try:
                return float(metrics[key])
            except (TypeError, ValueError):
                return default
    return default


def run_benchmark(label: str, episodes: int, settings: dict) -> tuple[list[dict], dict]:
    torch.manual_seed(settings["seed"])
    random.seed(settings["seed"])
    trainer = server.ParallelTrainer(settings=settings)

    records: list[dict] = []
    failures: list[dict] = []
    t0 = time.perf_counter()
    for ep in range(1, episodes + 1):
        try:
            site_t0 = time.perf_counter()
            trainer.new_site()
            site_time = time.perf_counter() - site_t0
            ep_t0 = time.perf_counter()
            step_count = 0
            while True:
                res = trainer.step(trainer.generation_id, trainer.episode)
                step_count += 1
                # Break ONLY on the terminal event: `_finish_episode` (which runs the
                # learning step) fires on the next `step()` after all envs are done,
                # so `all(e.done)` is NOT a valid terminal signal — it skips learning.
                if res.get("type") == "episodeDone":
                    break
            ep_time = time.perf_counter() - ep_t0
            metrics = res.get("metrics", {}) if isinstance(res, dict) else {}
            perf = metrics.get("performanceTimings", {})
            cg_avg = 0.0
            learn_avg = 0.0
            if isinstance(perf, dict):
                cg = perf.get("candidateGeneration", {})
                learn = perf.get("learning", {})
                # StepProfiler stores durations in ms.
                cg_avg = float(cg.get("avg", 0.0)) / 1000.0 if isinstance(cg, dict) else 0.0
                learn_avg = float(learn.get("avg", 0.0)) / 1000.0 if isinstance(learn, dict) else 0.0
            records.append(
                {
                    "episode": ep,
                    "score": _safe_get(metrics, "score", "aggregateReward"),
                    "fillRatio": _safe_get(metrics, "fillRatio"),
                    "rentableRatio": _safe_get(metrics, "rentableRatio"),
                    "compactness": _safe_get(metrics, "compactness"),
                    "vocabSize": _safe_get(metrics, "vocabSize"),
                    "loss": float(getattr(trainer, "last_loss", 0.0)),
                    "advantage": float(getattr(trainer, "last_advantage", 0.0)),
                    "placements": _safe_get(metrics, "totalPlacements"),
                    "time_s": ep_time,
                    "site_gen_time_s": site_time,
                    "step_count": step_count,
                    "candidate_gen_avg_s": cg_avg,
                    "learning_avg_s": learn_avg,
                    "peak_rss_mb": peak_rss_mb(),
                }
            )
        except Exception as exc:  # noqa: BLE001 — benchmark must survive flaky episodes
            failures.append({"episode": ep, "error": type(exc).__name__, "message": str(exc)})
            print(f"[{label}] ep {ep:4d} FAILED: {type(exc).__name__}: {exc}", flush=True)
            continue
        if ep % 25 == 0 or ep == episodes:
            recent = records[-25:]
            avg_score = statistics.mean(r["score"] for r in recent)
            avg_fill = statistics.mean(r["fillRatio"] for r in recent) * 100.0
            elapsed = (time.perf_counter() - t0) / 60.0
            print(
                f"[{label}] ep {ep:4d}/{episodes} | score(25)={avg_score:6.2f} | "
                f"fill(25)={avg_fill:4.1f}% | ep_time={ep_time:5.2f}s | "
                f"elapsed={elapsed:6.2f}m | rss={peak_rss_mb():6.1f}MB",
                flush=True,
            )

    total_time = time.perf_counter() - t0
    scores = [r["score"] for r in records]

    def _mean_or(key: str, records_slice: list[dict], default: float = 0.0) -> float:
        return statistics.mean(r[key] for r in records_slice) if records_slice else default

    def last_50_mean(key: str) -> float:
        return _mean_or(key, records[-50:])

    summary = {
        "label": label,
        "episodes": episodes,
        "completed_episodes": len(records),
        "failed_episodes": len(failures),
        "failures": failures,
        "settings": {
            k: settings[k]
            for k in (
                "siteAreaTier",
                "boundaryType",
                "parallelEnvironments",
                "maxModules",
                "seed",
                "singleFloor",
                "bufferEpisodes",
                "learningRate",
            )
            if k in settings
        },
        "total_time_s": total_time,
        "mean_episode_time_s": _mean_or("time_s", records),
        "peak_rss_mb": peak_rss_mb(),
        "mean_score": statistics.mean(scores) if scores else 0.0,
        "final_score_50": last_50_mean("score"),
        "final_fill_50": last_50_mean("fillRatio") * 100.0,
        "final_rentable_50": last_50_mean("rentableRatio") * 100.0,
        "mean_loss": _mean_or("loss", records),
        "final_loss_50": _mean_or("loss", records[-50:]),
        "mean_advantage": _mean_or("advantage", records),
        "mean_placements": _mean_or("placements", records),
        "mean_site_gen_time_s": _mean_or("site_gen_time_s", records),
        "mean_step_count": _mean_or("step_count", records),
        "mean_candidate_gen_s": _mean_or("candidate_gen_avg_s", records),
        "mean_learning_s": _mean_or("learning_avg_s", records),
        "milestones": {},
    }
    for m_ep in (25, 50, 100, 200, 300, 400, 500):
        if m_ep <= episodes:
            window = records[max(0, m_ep - 25) : m_ep]
            if window:
                summary["milestones"][str(m_ep)] = {
                    "score_25": round(statistics.mean(r["score"] for r in window), 2),
                    "fill_25": round(statistics.mean(r["fillRatio"] for r in window) * 100.0, 1),
                }
    return records, summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--episodes", type=int, default=300)
    parser.add_argument("--lr", type=float, default=None, help="Override learningRate")
    parser.add_argument("--out-dir", default="benchmarks/run_results")
    args = parser.parse_args()

    settings = default_settings()
    if args.lr is not None:
        settings["learningRate"] = args.lr
    records, summary = run_benchmark(args.label, args.episodes, settings)

    os.makedirs(args.out_dir, exist_ok=True)
    out_path = os.path.join(args.out_dir, f"{args.label}.json")
    with open(out_path, "w") as f:
        json.dump({"summary": summary, "records": records}, f, indent=2)

    print("\n" + "=" * 96)
    print(f"SUMMARY [{args.label}]  ({args.episodes} episodes)")
    print("=" * 96)
    print(f"  completed / failed  : {summary['completed_episodes']} / {summary['failed_episodes']}")
    print(f"  total time          : {summary['total_time_s']/60:8.2f} min")
    print(f"  mean episode time   : {summary['mean_episode_time_s']:8.2f} s")
    print(f"  peak RSS            : {summary['peak_rss_mb']:8.1f} MB")
    print(f"  mean score          : {summary['mean_score']:8.2f}")
    print(f"  final score (50)    : {summary['final_score_50']:8.2f}")
    print(f"  final fill   (50)   : {summary['final_fill_50']:8.1f} %")
    print(f"  final rentable (50) : {summary['final_rentable_50']:8.1f} %")
    print(f"  mean loss           : {summary['mean_loss']:8.4f}")
    print(f"  final loss (50)     : {summary['final_loss_50']:8.4f}")
    print(f"  mean advantage      : {summary['mean_advantage']:8.3f}")
    print(f"  mean placements/ep  : {summary['mean_placements']:8.1f}")
    print(f"  mean site-gen time  : {summary['mean_site_gen_time_s']:8.3f} s")
    print(f"  mean step count/ep  : {summary['mean_step_count']:8.1f}")
    print(f"  mean cand-gen/step  : {summary['mean_candidate_gen_s']:8.3f} s")
    print(f"  mean learning/step  : {summary['mean_learning_s']:8.3f} s")
    for m_ep, m in summary["milestones"].items():
        print(f"  milestone ep {m_ep:>3}     : score={m['score_25']:6.2f}  fill={m['fill_25']:5.1f}%")
    print(f"\n  results -> {out_path}")


if __name__ == "__main__":
    main()
