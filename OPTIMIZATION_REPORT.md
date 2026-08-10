# v0.8.0 optimization report

## Outcome and lineage

v0.8.0 turns the old core-stacking idea into an explicit building transaction on the optimized Module Lab kernel. It does not build directly on the slow v0.6-c implementation: v0.6-c supplies the behavioral goal, while v0.8.0 uses the current exact geometry, bounded proposal search, native broad phases, terminal-only BPE, and Monte Carlo actor–critic.

The output has three independently checkable claims:

1. targeted tests establish the exact 4–8-floor stacking invariants, rollback behavior, and irregular-site transaction policy; and
2. a same-host, same-settings, same-seed historical comparison measures the genuine archived v0.6-c against final v0.8.0; and
3. a separate 10-episode artifact establishes absolute runtime, memory, and early quality for the harder default four-floor workload.

The matched historical result is a **6.539320468817443x** episode-wall speed-up and a **14.069987717848928x** action-step speed-up. The v0.6-c source was recovered from commit `49692e04d379ec91ae349e3d446a6d63d6ad46c4`, subtree `rl_v0.6-c`; the current row uses the final v0.8.0 folder. Comparing v0.8.0 with v0.8.1 or root v0.7-D would be less meaningful because those variants do not pursue the same building-core goal.

## Exact building action

A shared core candidate is keyed by:

```text
(module id, rotation angle, local anchor x, local anchor y)
```

For each proposed signature, v0.8.0 constructs the candidate independently on every floor and applies the same authoritative checks used for ordinary placement. The world-space UI offset is irrelevant; the local polygon is the audited object.

The initial proposal path intersects the original raster-cell keys from all floors to obtain a bounded set of high-clearance anchors, but this is only a broad phase. Every transform must still pass vector containment, hole avoidance, positive-area collision, core spacing, alignment, neighbor/contact, and final site-cell materialization on every floor. Up to 512 signatures are proposed and at most 16 exact shared candidates are retained for the building policy.

### First and later cores

- Multi-floor generation first samples one learned core module for the building. Settings validation ensures the active edge constraints can form the required minimum 24 m² core.
- The first action is mandatory: there is no no-stack option until every floor owns the first locked core.
- The gate pools the per-floor feature rows for each shared transform. Selecting one signature creates one categorical decision, one log-probability term, and one stack record, while emitting one placement per floor.
- Floor-local proposal and repair paths are forbidden from introducing cores in multi-floor mode.
- A second stack is eligible only when every floor has exactly one core and at least `SECOND_CORE_MIN_ROOMS = 6` rooms. At that point the gate may select a shared transform or a building-level no-stack action. No third stack is offered by this policy.

The primary core module and its already-proven site relationship persist across episodes on the same generation. The next episode prevalidates the empty-floor transform again before clearing the old placements. A new site or settings generation samples a new building transaction.

### Actor–critic accounting

Building placement decisions use the reserved trajectory index `-1`; floor trajectories retain their own indices. During terminal learning, log-probabilities are summed within each trajectory and independent trajectories are averaged. The primary core's shape log-probability is stored once as a building-shape decision and is not divided by floor count. This prevents an eight-floor stack from contributing twice the policy weight of a four-floor stack.

The critic predicts normalized terminal score from the pooled floor descriptors. The update uses clipped advantage, smooth-L1 value loss, normalized placement entropy, and a gradient-norm cap of 2. It is a Monte Carlo actor–critic, not PPO, TD, GAE, or off-policy replay; exact terminal geometry remains the return source.

Checkpoint format 5 includes the critic, learner telemetry, bounded reward-reference state, and CPU/available-accelerator RNG state. Loading requires PyTorch 2.6 or newer, uses its restricted weights-only decoder, limits input to 64 MiB, validates tensor/scalar state plus Adam group and moment invariants, and commits transactionally—including v0.8.0's core-stack generation state. Saves use atomic temporary-file replacement with partial-file cleanup. Older runtimes fail closed because their weights-only loader is affected by [CVE-2025-32434](https://github.com/pytorch/pytorch/security/advisories/GHSA-53q9-r3pm-6pq6). Format-3 checkpoints can load the actor while initializing a genuinely fresh critic/optimizer; historical learning rates are clamped to the stable range and marginal 20 m² core settings are expanded to the current 24 m² feasibility envelope. Format-4 checkpoints remain loadable and reset the reward references they did not store.

## Whole-site irregular-boundary transaction

Before committing a multi-floor generation, v0.8.0 performs this transaction:

1. Generate every requested floor boundary and atrium from deterministic attempt/floor seeds.
2. Synthesize the first learned building core.
3. Reset temporary environments with that module.
4. Search for at least one exact shared local transform.
5. If none exists, discard the complete temporary group and repeat with new seeds for **all** floors.
6. Commit settings, generation ID, environments, dictionary, shape policy terms, and prevalidated stacks only after the group succeeds.

There are at most 24 complete site attempts, indexed 0–23. The requested boundary family is passed unchanged to every attempt. A lobed, L-, U-, T-, convex, or free-form request is never relaxed to a rectangle, individual floors are never swapped into an otherwise rejected group, and boundaries are not enlarged. If all attempts fail, `CoreStackingError` leaves the previous generation, sites, and dictionary unchanged.

For the measured seed-123 configuration, deterministic initialization reported:

| Initial core audit field | Value |
|---|---:|
| Enabled | true |
| Status / mode | ready / exact-shared-transform |
| Floor count | 4 |
| Boundary policy | whole-site-resample |
| `siteResampleAttempts` | 3 |
| Exact initial candidates | 2 |
| Pre-step stacks / locked cores | 0 / 0 |
| Exact local alignment / violations | true / 0 |

`siteResampleAttempts = 3` is the successful zero-based attempt index: three complete groups were rejected and the fourth was accepted. A matching native-status probe reported ABI 3 available and enabled with no load error.

The matching first live step produced four placements, one stack record, four locked cores, exact local alignment, `decisionScope: "building"`, and `logProbTerms: 1`. This checks the distinction between a four-floor mutation and a single learned action directly rather than inferring it from placement counts.

## Atomic stack commit

Selection is not permission to mutate blindly. The chosen signature is revalidated against the live state immediately before placement. Each floor then captures only placement-owned mutable state:

- placements, placement lookup, AABBs, spatial buckets, and adjacency;
- occupied cells, filled/rentable area, module-use counters, and core IDs;
- attachment edges, angle/placement indexes, order/cursor state; and
- done/proposal-failure scalars.

Sites, boundary polygons, dictionaries, RNGs, and model parameters are not deep-copied. If any floor placement raises, all targeted checkpoints are restored and neither the building decision nor stack audit is appended. Targeted tests inject a failure on the second floor and compare every captured structure before and after rollback.

## Shared optimization kernel

### Native and broad-phase geometry

The optional ABI-3 C library accelerates positive-interior polygon overlap, concave-site containment with split intervals, longest/total shared overlap, tolerant symmetric segment overlap, and point-to-segment distance. Packed native buffers are value-keyed and cached; differential tests compare the C path to the deterministic Python reference over contact, holes, concavity, long-coordinate tolerances, and randomized polygons.

Candidate rejection proceeds from cheap to expensive: cached rotation/site bounds, placement AABB and spatial-bucket lookup, exact vector predicates, then rasterization only for a legal survivor. Incremental adjacency and exposed residual edges avoid repeated all-placement scans. The angle-indexed frontier exposes a rotating stratified view of at most 12 entries, preventing the same recent edges from monopolizing every bounded query.

### Parallel placement loop and BPE

Active floors generate candidates concurrently and the placement head scores the combined legal rows in one tensor call. Torch CPU execution defaults to one intra-op thread for the small policy batches.

Full layout-graph extraction and BPE merging occur at episode completion or explicit paused evaluation, not after each placement. Per-step telemetry retains `bpeMerge = 0` so the deferred work is visible. BPE rewards exactly +3 per globally reused merged-module occurrence; triangle and dictionary-cap penalties remain terminal components.

### Deterministic reward and diagnostics

Generation time, size-normalized time, profiler phase timing, and memory are telemetry only. Reward uses deterministic frontier growth and geometry/quality components, so workstation load or device choice does not directly change the target. Repeated paused evaluation is state-pure.

The hidden `Ctrl/Cmd+Shift+D` panel exposes score history, reward bars, candidate evaluations, native status, process/accelerator memory, actor/critic telemetry, and profiler averages/maxima/counts. Core-specific invariants are exported in the `coreStacking` protocol audit rather than inferred from canvas coordinates.

## Matched historical v0.6-c comparison

Sources:

- genuine v0.6-c: [`benchmark_results/historical_v0.6c_seed808_10ep.json`](benchmark_results/historical_v0.6c_seed808_10ep.json) and [`benchmark_results/historical_v0.6c_seed808_10ep.csv`](benchmark_results/historical_v0.6c_seed808_10ep.csv)
- final v0.8.0: [`benchmark_results/v0.8.0_seed808_matched_v06c_10ep.json`](benchmark_results/v0.8.0_seed808_matched_v06c_10ep.json) and [`benchmark_results/v0.8.0_seed808_matched_v06c_10ep.csv`](benchmark_results/v0.8.0_seed808_matched_v06c_10ep.csv)

The historical code was recovered from commit `49692e04d379ec91ae349e3d446a6d63d6ad46c4`, subtree `rl_v0.6-c`. Both runs used the same Linux host, Python 3.10.18, Torch 2.1.0+cu121, CPU device, seed 808, zero warm-up episodes, and 10 measured episodes. Shared settings were lobed boundaries, no atrium, four floors, 10 maximum modules per floor, dictionary cap 6, and 90-degree angle steps.

The artifacts were produced separately rather than by one combined controller invocation, so this is a matched cross-artifact comparison, not a paired-episode statistical test. Their workload, seed, interpreter, host, and timing implementation match. The historical run used a 40-step controller safety cap and the current run used 2000; no episode approached either cap—the observed maxima were 10 and 17 action steps—so this did not truncate either sample.

### Timing

| Metric | Genuine v0.6-c | Final v0.8.0 | Ratio |
|---|---:|---:|---:|
| Episode wall mean, s | 5.3411565833899655 | 0.8167754751979374 | 6.539320468817443x |
| Episode wall p50, s | 5.495239505980862 | 0.8016204159939662 | — |
| Episode wall p95, s | 7.708047809638082 | 1.0205294168845283 | — |
| Episode wall min, s | 2.780117426009383 | 0.6745507380110212 | — |
| Episode wall max, s | 8.238769116986077 | 1.0903770389850251 | — |
| Episodes per second | 0.18707200544290747 | 1.218310244698204 | — |
| Action-step mean, s | 0.5277815892453012 | 0.03751116204428289 | 14.069987717848928x |
| Action-step p50, s | 0.5252660679980181 | 0.034650760993827134 | — |
| Action-step p95, s | 1.0018451273092066 | 0.07413469078019258 | — |
| All step-call p50, s | 0.4810997589956969 | 0.035289695020765066 | — |
| All step-call p95, s | 0.9797533814096823 | 0.17007169941207378 | — |
| Action steps / terminal calls | 95 / 10 | 165 / 10 | — |
| Total measured wall, s | 53.45535253296839 | 8.208089888037648 | — |

Mean episode wall time fell by 84.70789121333829%. The current run executed 165 action steps versus 95 in the historical run, yet its mean action step was 92.89267325563179% faster. That per-step result helps separate kernel/proposal improvements from early episode termination.

### Quality, work, and diversity

| Metric | Genuine v0.6-c | Final v0.8.0 |
|---|---:|---:|
| Composite score mean | 25.81494 | 39.34408 |
| Composite score p50 | 33.6699 | 40.66305 |
| Fill ratio mean | 0.191089169989359 | 0.3639566176192635 |
| Rentable ratio mean | 0.4612095454999678 | 0.8479913144706932 |
| Topology-valid rate | 1.0 | 1.0 |
| Topology penalty mean | 0.0 | 0.0 |
| Module count mean | 38.0 | 29.3 |
| Dictionary length mean | 6.0 | 3.4 |
| BPE bonus / reused occurrences mean | 22.5 / 7.5 | 20.4 / 6.8 |
| Unmerged triangles / penalty mean | 2.3 / 4.6 | 3.7 / 7.4 |
| Triangle ratio mean | 0.0984144056825796 | 0.8624718993115295 |
| Core / room placement counts | 152 / 228 | 40 / 253 |
| Unique module / placement shape signatures | 15 / 20 | 6 / 6 |
| Unique action / layout / dictionary hashes | 10 / 10 / 10 | 10 / 10 / 7 |

Mean composite score increased by 13.529139999999998, fill by 0.1728674476299045, and rentable ratio by 0.3867817689707254. Both runs were topology-valid in all ten episodes. The current implementation reached those results with fewer final placements and slightly less immediate BPE repetition.

This is not action-for-action semantic parity. The historical final layouts contained 152 core placements, while exact v0.8.0 contained 40—one locked four-floor primary stack per episode. v0.8.0 also ended with 29.3 rather than 38.0 mean placements. Those differences are part of the intended algorithm correction, but they mean the 6.539320468817443x number is end-to-end configured-workload speed-up, not the isolated speed of identical trajectories. The 14.069987717848928x action-step result is the cleaner hot-loop comparison. Composite reward definitions and learning updates also evolved, so fill, rentable ratio, topology, and component metrics should accompany the headline score.

### Memory

| Metric, bytes | Genuine v0.6-c | Final v0.8.0 |
|---|---:|---:|
| RSS at measurement start | 524640256 | 524062720 |
| Observed RSS peak | 538607616 | 581517312 |
| RSS at end | 538439680 | 581517312 |
| `tracemalloc` start | 96925275 | 96953034 |
| `tracemalloc` peak | 101428315 | 115187171 |
| `tracemalloc` peak growth | 4503040 | 18234137 |

v0.8.0 used more measured memory in this comparison. The difference includes Python/Torch runtime state and the new critic, cached geometry buffers, exact stack candidates, and incremental indexes; the artifacts do not isolate those contributors. Neither run used accelerator memory.

The historical server emitted no internal phase profiler records, so phase-by-phase speed-up is not reported. Only the common controller wall timers are compared.

## Harder default-setting absolute run

Source artifacts:

- [`benchmark_results/v0.8.0_seed123_10ep.json`](benchmark_results/v0.8.0_seed123_10ep.json)
- [`benchmark_results/v0.8.0_seed123_10ep.csv`](benchmark_results/v0.8.0_seed123_10ep.csv)

Configuration: lobed boundaries, agent-selected atria, `singleFloor=false`, 4 floors, `maxModules=130`, learning rate 0.001, 3–9 m edges, at most 8 edges, `dictCap=10`, `angleStep=15`, `coreSpacing=8`, `travelLimit=12`, corridors and stop disabled, seed 123, zero warm-up episodes, and 10 measured episodes.

Environment recorded by the artifact: Linux 6.8, Python 3.10.18, Torch 2.1.0+cu121, `device=cpu`. The processor model is not recorded. Native ABI 3 was loaded and enabled in the matching deterministic initialization probe. No MPS, CUDA, second-GPU, or eight-floor performance measurement was made.

### Timing

| Metric | Exact artifact value |
|---|---:|
| Episode wall mean, s | 1.4606903691019397 |
| Episode wall p50, s | 1.3355903929914348 |
| Episode wall p95, s | 2.0379458730836633 |
| Episode wall min, s | 1.179163855034858 |
| Episode wall max, s | 2.0896430169814266 |
| Episodes per second | 0.6828369809729088 |
| Action-step mean, s | 0.04786676697794495 |
| Action-step p50, s | 0.044811322004534304 |
| Action-step p95, s | 0.0838590411003679 |
| All step-call p50, s | 0.045586714026285335 |
| All step-call p95, s | 0.1386718439782205 |
| Action steps / terminal calls | 190 / 10 |
| Total measured wall, s | 14.644783862982877 |

The action-step mean is 47.86676697794495 ms, below the project's 50 ms average-step target for this workload. Mean episode wall time is still 1.4606903691019397 seconds; it does not meet the old 250 ms episode aspiration. The workload completed an average 19.7 placements across four floors rather than reaching the configured 130-per-floor cap, so it is an early-termination workload, not a 520-placement stress test.

Selected count-weighted profiler averages:

| Phase | Mean ms | Sample count |
|---|---:|---:|
| Candidate generation | 7.36669946466309 | 530 |
| Site boundary | 0.09832805494370107 | 3924 |
| Overlap/collisions | 0.7073197898428382 | 3924 |
| Policy inference | 0.16691207971521899 | 190 |
| Shape synthesis | 15.722651778564392 | 439 |
| Placement commit | 0.45921463095168075 | 101 |
| Step BPE | 0.0 | 190 |
| Step total | 47.50626966185672 | 190 |
| Terminal metrics | 10.11400229181163 | 10 |
| Episode BPE | 48.1212561018765 | 10 |
| Learning | 36.18427330511622 | 10 |
| Next-episode dictionary/core preflight | 220.80462881713174 | 10 |
| Episode total | 1457.470546598779 | 10 |

The legacy `dictSynthesis` profiler label includes the exact next-episode primary-core preflight. At 220.80462881713174 ms it is the largest named terminal phase and a clear target for future cache or proposal reuse, provided revalidation semantics are preserved.

### Quality and diversity

| Metric | Exact artifact value |
|---|---:|
| Composite score mean | 31.719450000000002 |
| Composite score p50 / p95 | 33.6542 / 38.282379999999996 |
| Raw score mean | 19.770131989906165 |
| Fill ratio mean | 0.25898392102244655 |
| Rentable ratio mean | 0.7543502830836528 |
| Topology-valid rate | 1.0 |
| Topology penalty mean | 0.0 |
| Module count mean | 19.7 |
| Dictionary length mean | 3.7 |
| Candidate evaluations mean | 1886.2 |
| BPE bonus / reused occurrences mean | 15.0 / 5.0 |
| BPE rounds mean | 2.5 |
| Unmerged triangles / penalty mean | 1.7 / 3.4 |
| Triangle ratio mean | 0.04449380751424684 |
| Core / room placement counts | 40 / 157 |
| Unique module / placement shape signatures | 20 / 26 |
| Unique action / layout / dictionary hashes | 10 / 10 / 8 |

Forty core placements across ten four-floor episodes is exactly four core placements per episode. The benchmark artifact does not itself serialize the `coreStacking` audit; targeted core tests independently verify that the four placements are one locked building action with one policy term and exact local equality. All ten episodes were topology-valid, and every episode had a unique action and layout hash. This is evidence of early-run variation, not proof of converged policy diversity.

### Memory

| Metric | Exact artifact value, bytes |
|---|---:|
| RSS at measurement start | 536518656 |
| Observed RSS peak | 583000064 |
| RSS at end | 583000064 |
| `tracemalloc` start | 100998268 |
| `tracemalloc` peak | 114098615 |
| `tracemalloc` peak growth | 13100347 |

These figures include the Python and Torch runtimes. Accelerator dictionaries were empty because the run used CPU.

## Reproduction

From `v0.8.0`, build the native library. Reproduce the matched current row with:

```bash
python3 build_native.py
python3 scratch/benchmark.py \
  --module-dir v0.8.0=. \
  --episodes 10 \
  --warmup 0 \
  --seed 808 \
  --settings '{"boundaryType":"lobed","atriumPolicy":"none","parallelEnvironments":4,"maxModules":10,"dictCap":6,"angleStep":90.0}' \
  --max-steps 2000 \
  --episode-timeout 120 \
  --run-timeout 1260 \
  --json-out benchmark_results/repro_v0.8.0_seed808_matched_v06c_10ep.json \
  --csv-out benchmark_results/repro_v0.8.0_seed808_matched_v06c_10ep.csv
```

To reproduce the historical row, first export the exact subtree from a checkout that contains the archived commit:

```bash
baseline_dir=$(mktemp -d /tmp/v06c-genuine.XXXXXX)
git archive 49692e04d379ec91ae349e3d446a6d63d6ad46c4 rl_v0.6-c \
  | tar -x -C "$baseline_dir" --strip-components=1
```

Then, from `v0.8.0` in the same shell, run the current benchmark controller against the export:

```bash
python3 scratch/benchmark.py \
  --module-dir "historical-v0.6-c=$baseline_dir" \
  --episodes 10 \
  --warmup 0 \
  --seed 808 \
  --settings '{"boundaryType":"lobed","atriumPolicy":"none","parallelEnvironments":4,"maxModules":10,"dictCap":6,"angleStep":90.0}' \
  --max-steps 40 \
  --episode-timeout 120 \
  --json-out benchmark_results/repro_historical_v0.6c_seed808_10ep.json \
  --csv-out benchmark_results/repro_historical_v0.6c_seed808_10ep.csv
```

The checked-in historical JSON/CSV are unchanged copies of that run's output. Their `moduleDir` records the temporary absolute path used during the original execution; it is provenance, not a path expected to exist on another machine.

Reproduce the harder default-setting row with new artifact names:

```bash
python3 build_native.py
python3 scratch/benchmark.py \
  --module-dir v0.8.0=. \
  --episodes 10 \
  --seed 123 \
  --settings '{"allowCorridors":false,"allowStop":false,"angleStep":15.0,"atriumPolicy":"agent","boundaryType":"lobed","coreSpacing":8.0,"dictCap":10,"learningRate":0.001,"maxEdge":9.0,"maxEdges":8,"maxModules":130,"minEdge":3.0,"parallelEnvironments":4,"publicMode":false,"singleFloor":false,"travelLimit":12}' \
  --json-out benchmark_results/repro_v0.8.0_seed123_10ep.json \
  --csv-out benchmark_results/repro_v0.8.0_seed123_10ep.csv
```

Core and native contracts:

```bash
python3 -m unittest discover -s tests -p "test_core_stacking.py" -v
python3 -m unittest discover -s tests -p "test_native_geometry.py" -v
python3 -m unittest discover -s tests -p "test_optimization.py" -v
```

The final verified non-WebSocket suite rebuilt native ABI 3 and ran 157 tests successfully with 2 intentional legacy skips:

```bash
python3 -m unittest \
  tests.test_benchmark tests.test_bpe_merge tests.test_core_stacking \
  tests.test_frontend_contract tests.test_geometry tests.test_graph_evaluation \
  tests.test_learned_policy tests.test_native_geometry tests.test_optimization \
  tests.test_trainer tests.test_v06b_dynamic tests.test_v06d_custom
```

The two `tests.test_websocket` cases are excluded because this restricted runner blocks inside FastAPI/Starlette `TestClient.__enter__`, including for a minimal empty FastAPI app. That is an environment/dependency limitation, not a passing integration result; rerun them with a normal host or real server process.

The benchmark's fresh child process matters: it prevents baseline/module imports, native-library paths, Torch pools, and caches from contaminating a run.

## Graph decision

The recovered endpoint-only graph was not integrated. On the measured 96-module probe in the separate graph evaluation, its query was 13.6x slower than the bounded residual-edge query and emitted 79% more anchors, only for exact geometry to reject the extras. The current angle index already supplies the useful graph broad phase. v0.8.0 implements the deterministic rotating-stratified sample recommended by that study. Full data and GNN acceptance criteria are in [GRAPH_EVALUATION.md](GRAPH_EVALUATION.md).

## Limitations and next work

- The genuine v0.6-c and current runs match hardware, interpreter, seed, floor count, and settings, but not exact action semantics. Treat 6.539320468817443x as configured-workload speed-up and 14.069987717848928x as the closer per-action hot-loop comparison.
- Each benchmark covers one seed, the first 10 episodes, four floors, and CPU. Neither measures 8 floors, Apple CPU/MPS, CUDA, either RTX GPU, or multi-GPU scaling.
- Floor count is fixed within a generation. Users can atomically switch from 4 to 8 between settings generations, but v0.8.0 does not randomly vary it each episode.
- Accepting only sites with a common local core transform can bias the retained irregular-site sample toward larger common feasible regions. It preserves boundary families and never relaxes to rectangles, but the acceptance filter is still real.
- The primary core persists across episodes on one site. This guarantees feasibility but reduces core-shape variation until a new site/settings generation.
- The optional second core may be rare because all floors must independently reach six rooms and share another exact transform.
- The bounded frontier intentionally trades exhaustive legal-action recall for predictable work. Rotation/stratification prevents permanent edge starvation but is not a lossless scan.
- Terminal core preflight and BPE remain substantial costs. Any cache must retain immediate live-state revalidation and atomic rollback.
- The 10-episode result establishes early behavior, not convergence or lower-gradient variance over a long learning curve. A multi-seed, fixed-wall-budget comparison is still required before preferring this learner to PPO/GAE or TD alternatives.
- One trainer uses one accelerator. Two `cuda:N` processes are independent policies, not one distributed building batch.
- In the restricted development sandbox, FastAPI `TestClient` WebSocket integration can block on cross-thread event-loop wakeup. Use direct trainer tests or a real process there and rerun WebSocket integration on a normal host/CI runner.
