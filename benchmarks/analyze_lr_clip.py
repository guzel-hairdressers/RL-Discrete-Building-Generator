#!/usr/bin/env python3
"""LR-schedule + ratio-clip analysis: does it damp the A2C mid-run collapse?

Compares cap_base (the deterministic 0.003 control) against the 4 new runs.
Key question: does cosine LR annealing / the epsilon=0.2 ratio clip reduce the
mid-run volatility collapse (eps ~150-350 at 0.003) and raise final-50 without
the candidate-coverage cost?
"""
import json
import os
import statistics

RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_results")
CONTROL = os.path.join(RESULTS, "cap_base.json")

RUNS = ["cap_base", "lr_0001", "lr_cosine", "lr_clip", "lr_cosine_clip"]


def load(label):
    path = CONTROL if label == "cap_base" else os.path.join(RESULTS, f"{label}.json")
    with open(path) as f:
        return json.load(f)


def window_mean(records, m, key="score", window=25):
    recent = [r[key] for r in records if m - window < r["episode"] <= m]
    return statistics.mean(recent) if recent else float("nan")


def collapse_metrics(records):
    """Volatility / collapse indicators over the mid-run region (eps 150-350)."""
    mid = [r["score"] for r in records if 150 <= r["episode"] <= 350]
    mid_mean = statistics.mean(mid) if mid else float("nan")
    # Worst 25-episode window mean anywhere in the run.
    worst = min(
        (window_mean(records, m) for m in range(25, 501)),
        default=float("nan"),
    )
    # Standard deviation of per-episode scores in the mid-run region.
    mid_std = statistics.pstdev(mid) if len(mid) > 1 else float("nan")
    return mid_mean, worst, mid_std


def main():
    data = {}
    for label in RUNS:
        p = CONTROL if label == "cap_base" else os.path.join(RESULTS, f"{label}.json")
        if not os.path.exists(p):
            print(f"MISSING {p} (still running?)")
            continue
        data[label] = load(label)
    if "cap_base" not in data:
        print("cap_base (control) missing — cannot interpret.")
        return
    order = [l for l in RUNS if l in data]

    base_s = data["cap_base"]["summary"]

    print("=" * 92)
    print("COST  (delta vs cap_base)")
    print("=" * 92)
    hdr = (f"{'run':<16}{'total(min)':>11}{'ep(s)':>7}{'d%':>6}{'RSS(MB)':>9}{'lr':>9}{'clip':>6}")
    print(hdr)
    print("-" * len(hdr))
    for label in order:
        s = data[label]["summary"]
        cfg = s["settings"]
        dmg = 100.0 * (s["mean_episode_time_s"] / base_s["mean_episode_time_s"] - 1.0)
        print(f"{label:<16}{s['total_time_s']/60:>11.1f}{s['mean_episode_time_s']:>7.2f}"
              f"{dmg:>6.0f}%{s['peak_rss_mb']:>9.0f}"
              f"{str(cfg.get('lrSchedule', 'const')):>9}{cfg.get('ratioClip', 0.0):>6}")

    print()
    print("=" * 92)
    print("QUALITY  (delta vs cap_base)")
    print("=" * 92)
    hdr2 = (f"{'run':<16}{'meanScore':>10}{'d':>7}{'fin50Score':>11}{'d':>6}"
            f"{'fin50Fill%':>11}{'place/ep':>9}")
    print(hdr2)
    print("-" * len(hdr2))
    for label in order:
        d = data[label]
        s = d["summary"]
        pl = statistics.mean(r["placements"] for r in d["records"])
        dsc = s["mean_score"] - base_s["mean_score"]
        dfin = s["final_score_50"] - base_s["final_score_50"]
        print(f"{label:<16}{s['mean_score']:>10.2f}{dsc:>+7.2f}{s['final_score_50']:>11.2f}"
              f"{dfin:>+6.2f}{s['final_fill_50']:>11.1f}{pl:>9.1f}")

    print()
    print("=" * 92)
    print("COLLAPSE REGION  (eps 150-350) — lower std / higher mid mean = damped")
    print("=" * 92)
    hdr3 = (f"{'run':<16}{'mid(150-350)':>13}{'worstWin25':>11}{'midStd':>8}{'std d':>7}")
    print(hdr3)
    print("-" * len(hdr3))
    base_mid, base_worst, base_std = collapse_metrics(data["cap_base"]["records"])
    for label in order:
        mid, worst, std = collapse_metrics(data[label]["records"])
        print(f"{label:<16}{mid:>13.2f}{worst:>11.2f}{std:>8.2f}{std - base_std:>+7.2f}")

    print()
    print("=" * 92)
    print("SCORE TRAJECTORY  (25-episode window mean)")
    print("=" * 92)
    milestones = [25, 50, 100, 150, 200, 250, 300, 350, 400, 450, 500]
    hdr4 = f"{'run':<16}" + "".join(f"{m:>8}" for m in milestones)
    print(hdr4)
    print("-" * len(hdr4))
    for label in order:
        cells = [window_mean(data[label]["records"], m, "score") for m in milestones]
        row = f"{label:<16}" + "".join(f"{v:>8.2f}" if v == v else f"{'--':>8}" for v in cells)
        print(row)


if __name__ == "__main__":
    main()
