#!/bin/bash
set -u
cd /tmp/cap_sweep
mkdir -p /tmp/cap_sweep_results
# cap_base + cap_base2 (both DONE) are the deterministic control pair.
# These are the 5 cap variants, 500 eps each.
run() { label=$1; shift
  echo ">>> START $label ($*) $(date +%H:%M:%S)"
  PYTHONPATH=src python3 benchmarks/benchmark_300_episodes.py --label "$label" --episodes 500 "$@" --out-dir /tmp/cap_sweep_results 2>&1
  rc=$?
  echo ">>> DONE $label rc=$rc $(date +%H:%M:%S)"
}
run cap_cat24 --cat-limit 24
run cap_cat48 --cat-limit 48
run cap_edge24 --edge-window 24
run cap_edge48 --edge-window 48
run cap_wide48 --cat-limit 48 --edge-window 48
echo ">>> ALL_SWEEP_DONE"
