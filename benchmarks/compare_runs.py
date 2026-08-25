"""Compare benchmark run results side by side.

Usage:
    python3 benchmarks/compare_runs.py baseline fix_snapshot a2c
"""

from __future__ import annotations

import json
import os
import sys

RUN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_results")


def load(label: str) -> dict:
    path = os.path.join(RUN_DIR, f"{label}.json")
    with open(path) as f:
        return json.load(f)["summary"]


def fmt(value, digits: int = 2) -> str:
    return f"{value:.{digits}f}"


def main(labels: list[str]) -> None:
    summaries = {label: load(label) for label in labels}

    def row(title: str, key: str, digits: int = 2, scale: float = 1.0):
        cells = " | ".join(
            fmt(summaries[label].get(key, 0.0) * scale, digits) for label in labels
        )
        print(f"{title:<28} | {cells}")

    print("=" * (28 + 12 * len(labels)))
    print(f"{'Metric':<28} | " + " | ".join(f"{label:<10}" for label in labels))
    print("=" * (28 + 12 * len(labels)))
    row("completed / failed", "completed_episodes", 0)
    row("mean score", "mean_score")
    row("final-50 score", "final_score_50")
    row("final-50 fill (%)", "final_fill_50", 1)
    row("final-50 rentable (%)", "final_rentable_50", 1)
    row("mean loss", "mean_loss", 4)
    row("final-50 loss", "final_loss_50", 4)
    row("mean advantage", "mean_advantage", 3)
    row("mean placements/ep", "mean_placements", 1)
    row("peak RSS (MB)", "peak_rss_mb", 1)
    row("mean ep time (s)", "mean_episode_time_s", 2)
    row("total time (min)", "total_time_s", 2, scale=1 / 60)
    print("=" * (28 + 12 * len(labels)))

    print("\nMilestone score (25-ep window):")
    milestones = sorted({m for s in summaries.values() for m in s["milestones"]})
    for m in milestones:
        cells = " | ".join(
            fmt(summaries[label]["milestones"].get(m, {}).get("score_25", 0.0))
            for label in labels
        )
        print(f"  ep {m:>4}               | {cells}")


if __name__ == "__main__":
    main(sys.argv[1:])
