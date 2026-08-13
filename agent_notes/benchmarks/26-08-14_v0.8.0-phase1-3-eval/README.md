# Benchmark Evaluation: v0.8.0 Phase 1-3 (PPO/GAE + BPE Regularization + Native Hotpaths + Dataset Recording)

**Date**: 2026-08-14  
**Hardware Platform**: macOS ARM64  
**Commit/Target**: `main` (`v0.8.0` with Phase 1-3 roadmap features)

---

## 1. Test Suite Results
* Total Unit Tests: **152 tests passed** (`OK (skipped=2)`).
* Total Test Execution Time: **2.95s**.

---

## 2. Execution Performance
* **10-Episode Benchmark (`benchmarks/benchmark.py`)**:
  * Wall time mean: `1.926s` across 10 episodes (~`192.6ms`/episode).
  * p50 episode time: `1.598s`.
  * Mean Score: `51.53 pts`.
  * Placement step p50: `55.68ms`.
  * Placement step p95: `136.51ms` (227 step policy/FFI calls).

---

## 3. Verified Roadmap Features
1. **Phase 1 (Learning Stability & Variance Reduction)**:
   - GAE ($\gamma=0.99, \lambda=0.95$) + batch advantage standardization.
   - PPO clipped surrogate loss ($\epsilon=0.2$).
   - Terminal reward assignment backpropagation.
2. **Phase 1C (BPE Regularization & Entropy Bonus)**:
   - Anti-sprawl constraints ($N \le 4$, compactness $\ge 0.15$, aspect ratio $\le 8.5$).
   - Module utilization Shannon entropy bonus ($+2.0 \times H_{\text{norm}}$).
   - Primitive module purging before vocabulary capacity checks.
3. **Phase 2 (C SAT & Collinear Hotpaths)**:
   - Single-pass `G.shared_overlap_pair` and `G.symmetric_segment_overlap`.
4. **Phase 3 (Data Trajectory Archiving & Lookahead Search)**:
   - Automated JSONL trajectory recording via `record_dataset_trajectory`.
   - Top-$k$ candidate lookahead beam search via `beamSearchWidth` parameter.
