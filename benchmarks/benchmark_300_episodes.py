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
    # Official quality-benchmark protocol (AGENTS.md): ANY tier, FREE boundary,
    # auto-changing procedural sites. Multi-floor path stays enabled.
    settings["siteAreaTier"] = "ANY"
    settings["boundaryType"] = "free"
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
    t0 = time.perf_counter()
    for ep in range(1, episodes + 1):
        trainer.new_site()
        ep_t0 = time.perf_counter()
        while True:
            res = trainer.step(trainer.generation_id, trainer.episode)
            if res.get("type") == "episodeDone" or all(e.done for e in trainer.environments):
                break
        ep_time = time.perf_counter() - ep_t0
        metrics = res.get("metrics", {}) if isinstance(res, dict) else {}
        records.append(
            {
                "episode": ep,
                "score": _safe_get(metrics, "score", "aggregateReward"),
                "fillRatio": _safe_get(metrics, "fillRatio"),
                "rentableRatio": _safe_get(metrics, "rentableRatio"),
                "compactness": _safe_get(metrics, "compactness"),
                "vocabSize": _safe_get(metrics, "vocabSize"),
                "time_s": ep_time,
                "peak_rss_mb": peak_rss_mb(),
            }
        )
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

    def last_50_mean(key: str) -> float:
        return statistics.mean(r[key] for r in records[-50:])

    summary = {
        "label": label,
        "episodes": episodes,
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
        "mean_episode_time_s": statistics.mean(r["time_s"] for r in records),
        "peak_rss_mb": peak_rss_mb(),
        "mean_score": statistics.mean(scores),
        "final_score_50": last_50_mean("score"),
        "final_fill_50": last_50_mean("fillRatio") * 100.0,
        "final_rentable_50": last_50_mean("rentableRatio") * 100.0,
        "milestones": {},
    }
    for m_ep in (25, 50, 100, 200, 300):
        if m_ep <= episodes:
            window = records[max(0, m_ep - 25) : m_ep]
            summary["milestones"][str(m_ep)] = {
                "score_25": round(statistics.mean(r["score"] for r in window), 2),
                "fill_25": round(statistics.mean(r["fillRatio"] for r in window) * 100.0, 1),
            }
    return records, summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--episodes", type=int, default=300)
    parser.add_argument("--out-dir", default="benchmarks/run_results")
    args = parser.parse_args()

    settings = default_settings()
    records, summary = run_benchmark(args.label, args.episodes, settings)

    os.makedirs(args.out_dir, exist_ok=True)
    out_path = os.path.join(args.out_dir, f"{args.label}.json")
    with open(out_path, "w") as f:
        json.dump({"summary": summary, "records": records}, f, indent=2)

    print("\n" + "=" * 96)
    print(f"SUMMARY [{args.label}]  ({args.episodes} episodes)")
    print("=" * 96)
    print(f"  total time          : {summary['total_time_s']/60:8.2f} min")
    print(f"  mean episode time   : {summary['mean_episode_time_s']:8.2f} s")
    print(f"  peak RSS            : {summary['peak_rss_mb']:8.1f} MB")
    print(f"  mean score          : {summary['mean_score']:8.2f}")
    print(f"  final score (50)    : {summary['final_score_50']:8.2f}")
    print(f"  final fill   (50)   : {summary['final_fill_50']:8.1f} %")
    print(f"  final rentable (50) : {summary['final_rentable_50']:8.1f} %")
    for m_ep, m in summary["milestones"].items():
        print(f"  milestone ep {m_ep:>3}     : score={m['score_25']:6.2f}  fill={m['fill_25']:5.1f}%")
    print(f"\n  results -> {out_path}")


if __name__ == "__main__":
    main()
