#!/usr/bin/env python3
"""Cap-sweep analysis: coverage (quality) vs cost (time/memory/cand-gen).

Compares the 6 sweep runs in /tmp/cap_sweep_results. cap_base (pure default,
no cap overrides) is the in-sweep control; every variant is measured against it
as delta.  NOTE: free_wins.json is NOT a valid per-episode baseline for the
07195f5d tree (known drift / latent divergence at ep 3) — it is only shown for
reference.  The edited tree was verified bit-identical to the pristine tree.
"""
import json
import os
import statistics

SWEEP_DIR = "/tmp/cap_sweep_results"


def load(path):
    with open(path) as f:
        return json.load(f)


def window_mean(records, m, key, window=25):
    recent = [r[key] for r in records if m - window < r["episode"] <= m]
    return statistics.mean(recent) if recent else float("nan")


def main():
    runs = ["cap_base", "cap_cat24", "cap_cat48", "cap_edge24", "cap_edge48", "cap_wide48"]
    data = {}
    for label in runs:
        p = os.path.join(SWEEP_DIR, f"{label}.json")
        if not os.path.exists(p):
            print(f"MISSING {p} (still running?)")
            continue
        data[label] = load(p)
    if not data:
        print("No sweep results yet.")
        return
    if "cap_base" not in data:
        print("cap_base (control) missing — cannot interpret deltas yet.")
        return
    base_s = data["cap_base"]["summary"]
    order = [l for l in runs if l in data]

    print("=" * 78)
    print("COST  (delta vs cap_base; higher = more expensive search)")
    print("=" * 78)
    hdr = (f"{'run':<12}{'cat':>4}{'edge':>5}{'total(min)':>11}{'ep(s)':>7}"
           f"{'d%':>6}{'RSS(MB)':>9}{'cg/step(s)':>11}")
    print(hdr)
    print("-" * len(hdr))
    for label in order:
        d = data[label]
        s = d["summary"]
        cg = statistics.mean(r["candidate_gen_avg_s"] for r in d["records"])
        cat = s["settings"].get("candidateCatLimit", "-")
        edge = s["settings"].get("candidateEdgeWindow", "-")
        dmg = 100.0 * (s["mean_episode_time_s"] / base_s["mean_episode_time_s"] - 1.0)
        print(f"{label:<12}{str(cat):>4}{str(edge):>5}{s['total_time_s']/60:>11.1f}"
              f"{s['mean_episode_time_s']:>7.2f}{dmg:>6.0f}%{s['peak_rss_mb']:>9.0f}{cg:>11.4f}")

    print()
    print("=" * 78)
    print("QUALITY  (delta vs cap_base; higher = better plans)")
    print("=" * 78)
    hdr2 = (f"{'run':<12}{'meanScore':>10}{'d':>6}{'fin50Score':>11}{'fin50Fill%':>11}"
            f"{'place/ep':>9}{'d':>5}")
    print(hdr2)
    print("-" * len(hdr2))
    for label in order:
        d = data[label]
        s = d["summary"]
        pl = statistics.mean(r["placements"] for r in d["records"])
        dsc = s["mean_score"] - base_s["mean_score"]
        dpl = pl - statistics.mean(r["placements"] for r in data["cap_base"]["records"])
        print(f"{label:<12}{s['mean_score']:>10.2f}{dsc:>+6.2f}{s['final_score_50']:>11.2f}"
              f"{s['final_fill_50']:>11.1f}{pl:>9.1f}{dpl:>+5.1f}")

    print()
    print("=" * 78)
    print("SCORE TRAJECTORY  (25-episode window mean)")
    print("=" * 78)
    milestones = [25, 50, 100, 200, 300, 400, 500]
    hdr3 = f"{'run':<12}" + "".join(f"{m:>8}" for m in milestones)
    print(hdr3)
    print("-" * len(hdr3))
    for label in order:
        cells = [window_mean(data[label]["records"], m, "score") for m in milestones]
        row = f"{label:<12}" + "".join(
            f"{v:>8.2f}" if v == v else f"{'--':>8}" for v in cells)
        print(row)


if __name__ == "__main__":
    main()
