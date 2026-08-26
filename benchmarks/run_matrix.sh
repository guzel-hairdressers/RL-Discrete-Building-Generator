#!/bin/bash
set -u
cd /tmp/lr_clip_sweep
mkdir -p /tmp/lr_clip_sweep_results
run() { label=$1; shift
  echo ">>> START $label ($*) $(date +%H:%M:%S)"
  PYTHONPATH=src python3 benchmarks/benchmark_300_episodes.py --label "$label" --episodes 500 "$@" --out-dir /tmp/lr_clip_sweep_results 2>&1
  rc=$?
  echo ">>> DONE $label rc=$rc $(date +%H:%M:%S)"
}
run lr_0001 --lr 0.001
run lr_cosine --lr-schedule cosine --lr-floor 0.001 --lr-horizon 500
run lr_clip --ratio-clip 0.2
run lr_cosine_clip --lr-schedule cosine --lr-floor 0.001 --lr-horizon 500 --ratio-clip 0.2
echo ">>> ALL_LRCLIP_DONE"
