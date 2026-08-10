# v0.8.1 optimization report

## Outcome

v0.8.1 removes the dominant repeated work from the v0.7-D placement loop without replacing its exact vector-geometry acceptance rules. The final-code representative result is a **5.919139752213579x** reduction in mean episode wall time on the 10-episode lobed workload when compared with the separately recorded, same-configuration root baseline. A 20-episode rectangular artifact retains a **5.067408708026263x** paired result from an earlier development point; it is useful historical paired evidence but does not measure the final release code.

Those are CPU results from one Linux machine, not projections for Apple MPS or RTX hardware. Quality moved differently by workload: the paired rectangular run improved composite score, fill, topology validity, and shape diversity; the harder lobed run improved fill, topology validity, and diversity but reduced rentable ratio and the composite BPE-weighted score.

## Scope and measurement method

The benchmark harness in `scratch/benchmark.py` starts each module/seed pair in a fresh Python process. It fixes `PYTHONHASHSEED`, Python random state, and Torch random state; completes optional warm-up episodes; and then records complete episodes until the requested count is reached. It collects:

- episode and step-call wall time, including p50/p95;
- count-weighted internal profiler phases;
- process RSS, `tracemalloc`, and available accelerator memory counters;
- score, fill, rentable ratio, topology, BPE, triangle, and candidate metrics;
- category entropy and unique module/placement shape signatures; and
- stable action, layout, and dictionary hashes.

All benchmark artifacts below report Linux 6.8, Python 3.10.18, Torch 2.1.0+cu121, and `device=cpu`. No CUDA or MPS run was measured during this pass.

The representative lobed artifact was generated from the final checked-in v0.8.1 code, including the `SECOND_CORE_MIN_ROOMS = 6` candidate filter. The earlier [`scratch/results_10ep_lobed_seed123_v081_finalcandidate.json`](scratch/results_10ep_lobed_seed123_v081_finalcandidate.json) and [`scratch/results_10ep_lobed_seed123_v081_candidatefilter.json`](scratch/results_10ep_lobed_seed123_v081_candidatefilter.json) are retained as historical evidence but are not used for the current headline. The root baseline is taken only from `results_10ep_lobed_seed123.json`; that file's earlier v0.8.1 contender is also superseded.

## Benchmark A: lobed boundary, first 10 episodes

Configuration: `boundaryType=lobed`, `atriumPolicy=agent`, `parallelEnvironments=4`, `maxModules=20`, `dictCap=10`, `angleStep=15`, seed 123, zero warm-up episodes, and 10 measured episodes.

Sources:

- root baseline: [`scratch/results_10ep_lobed_seed123.json`](scratch/results_10ep_lobed_seed123.json) and [`scratch/results_10ep_lobed_seed123.csv`](scratch/results_10ep_lobed_seed123.csv)
- final-code v0.8.1: [`scratch/results_10ep_lobed_seed123_v081_release.json`](scratch/results_10ep_lobed_seed123_v081_release.json) and [`scratch/results_10ep_lobed_seed123_v081_release.csv`](scratch/results_10ep_lobed_seed123_v081_release.csv)

The two rows are separate point-in-time runs with the same workload and host, not a single paired controller report. The speed-up is the exact ratio of their recorded mean episode times.

| Timing metric | Root v0.7-D baseline | Final v0.8.1 release |
|---|---:|---:|
| Episode wall mean, s | 7.604500205116347 | 1.2847306405077688 |
| Episode wall p50, s | 7.791219950013328 | 1.2129170919943135 |
| Episode wall p95, s | 10.240738575020805 | 1.8870772354974177 |
| Episode wall min, s | 5.54078847396886 | 0.6489926560316235 |
| Episode wall max, s | 10.330979028018191 | 1.9360698380041867 |
| Step-call p50, s | 0.2800938215223141 | 0.065461503516417 |
| Step-call p95, s | 1.4533910306054114 | 0.1309129648172528 |
| Episodes per second | 0.13139436119330128 | 0.7746841862097575 |
| Mean episode speed-up | 1.0x | 5.919139752213579x |

Quality and diversity means from those same runs:

| Metric | Root v0.7-D baseline | Final v0.8.1 release |
|---|---:|---:|
| Raw geometry/quality score | 19.515618350798185 | 20.34006515055671 |
| Final composite score | 47.1518 | 23.59606 |
| Fill ratio | 0.24981321331025047 | 0.29292073427368187 |
| Rentable ratio | 0.7318810787075865 | 0.6981978676144853 |
| Topology-valid rate | 0.0 | 1.0 |
| Mean topology penalty | 4.873028 | 0.0 |
| Mean BPE bonus | 36.77644494706176 | 14.4 |
| Mean reused BPE occurrences | 12.9 | 4.8 |
| Mean unmerged-triangle penalty | 3.8 | 11.2 |
| Mean unmerged triangles | 1.9 | 5.6 |
| Mean module count | 45.0 | 31.1 |
| Mean dictionary length | 4.0 | 9.6 |
| Mean candidate evaluations | 5795.7 | 4378.0 |
| Unique module shape signatures | 19 | 71 |
| Unique placement shape signatures | 32 | 103 |
| Unique action/layout hashes | 10 / 10 | 10 / 10 |

The lobed result is not a blanket quality win. Fill increased by 0.0431075209634314 and all 10 episodes were topology-valid, while rentable ratio fell by 0.0336832110931012. The raw score increased by 0.824446799758525, but the final composite score fell by 23.55574. The logged components show the main visible causes: the mean reuse bonus fell from 36.77644494706176 to 14.4 and the triangle penalty rose from 3.8 to 11.2. Because v0.8.1 also removes hardware time from reward, the final composite is not a pure like-for-like geometry metric; raw score, fill, rentable ratio, topology, and diversity should be inspected alongside it.

The release run produced 71 unique module-shape signatures and 103 placement-shape signatures, versus 19 and 32 in the baseline. That is materially more geometric variety over these 10 episodes, although it also means less immediate BPE repetition.

Selected count-weighted profiler averages explain where the wall-time reduction came from:

| Profiler phase, mean ms | Root v0.7-D baseline | Final v0.8.1 release |
|---|---:|---:|
| Candidate generation | 50.65104792396626 | 19.018010795306232 |
| Site-boundary checks | 38.23820675933785 | 0.39024465925740354 |
| Overlap/collision checks | 27.919441368582042 | 2.316665130336288 |
| Neighbor analysis | 6.717015716890568 | 0.050973928665608535 |
| Edge alignment | 1.8928284304595988 | 0.033508535782804945 |
| Feature extraction | 3.729162321296708 | 0.03389397364080396 |
| Policy inference | 7.8540294606442 | 0.22090964937686092 |
| Shape synthesis | 349.1808055064586 | 16.9024163473363 |
| Per-step BPE | 90.75717377575414 | 0.0 |
| Terminal BPE | 183.94655140582472 | 122.00650201411918 |
| Learning | 150.9999349131249 | 36.439332290319726 |
| Step total | 412.07772720706834 | 59.693068583470044 |
| Episode total | 7602.723605197389 | 1282.3845732957125 |

Memory is a secondary result because both processes include the Python and Torch runtimes. The observed RSS peak was 630947840 bytes for the root baseline and 591826944 bytes for the final release. `tracemalloc` peak was 135034604 and 117631795 bytes, while peak growth was 38792037 and 21004945 bytes, respectively. No accelerator-memory sample was present because both runs used CPU.

## Benchmark B: rectangular boundary, first 20 measured episodes

Configuration: `boundaryType=rect`, `atriumPolicy=none`, `parallelEnvironments=4`, `maxModules=10`, `dictCap=6`, `angleStep=90`, seed 812, one warm-up episode, and 20 measured episodes.

Sources: [`scratch/results_20ep_rect_seed812.json`](scratch/results_20ep_rect_seed812.json) and [`scratch/results_20ep_rect_seed812.csv`](scratch/results_20ep_rect_seed812.csv). Both variants were run by one controller, so the recorded comparison is paired by measured episode index. This artifact predates the final release measurement above; it is retained because pairing gives useful historical evidence, but its v0.8.1 row must not be presented as final-code performance.

| Timing metric | Root v0.7-D baseline | Historical v0.8.1 snapshot |
|---|---:|---:|
| Episode wall mean, s | 3.28561883145012 | 0.6483824417489814 |
| Episode wall p50, s | 3.2552898224967066 | 0.6549155310203787 |
| Episode wall p95, s | 3.8206527839152846 | 0.7626254646136659 |
| Episode wall min, s | 2.4741114859934896 | 0.5014499590033665 |
| Episode wall max, s | 3.989880404958967 | 0.7643361029913649 |
| Step-call p50, s | 0.2570610969851259 | 0.043457006016978994 |
| Step-call p95, s | 0.7008613813784904 | 0.22824161007010837 |
| Episodes per second | 0.3038610733528656 | 1.5305294505521627 |
| Paired mean speed-up | 1.0x | 5.067408708026263x |

| Quality metric | Root v0.7-D baseline | Historical v0.8.1 snapshot |
|---|---:|---:|
| Raw geometry/quality score | 18.063041780585134 | 23.48353614115165 |
| Final composite score | 45.20404 | 49.730689999999996 |
| Paired mean score delta | 0.0 | 4.526650000000001 |
| Fill ratio | 0.2888843070077018 | 0.3745877947740014 |
| Rentable ratio | 0.7954193047061673 | 0.7668160930879074 |
| Topology-valid rate | 0.3 | 0.95 |
| Mean topology-violation rate | 0.31050000000000005 | 0.013500000000000002 |
| Mean BPE bonus | 29.64072211310019 | 29.7 |
| Mean unmerged-triangle penalty | 0.6 | 3.3 |
| Mean module count | 39.3 | 37.4 |
| Mean candidate evaluations | 4599.85 | 2645.55 |
| Unique module shape signatures | 62 | 82 |
| Unique placement shape signatures | 76 | 89 |
| Unique action/layout hashes | 20 / 20 | 20 / 20 |

Here the speed-up did not require a composite-score concession: mean score increased by 4.526650000000001 and fill increased by 0.0857034877662996. Rentable ratio decreased by 0.0286032116182599 and triangle use increased, so the individual components still matter. Topology validity rose from 30% to 95%, candidate evaluations fell by 42.48616802721828%, and the run retained more unique shape signatures.

The action and layout hashes did not match between variants in either comparison. That is expected after proposal bounds, policy learning, reward, and shape availability changed; the hashes are regression identifiers, not a claim of action parity. Every measured episode within each run had a unique action and layout hash.

## Architecture changes

### 1. Exact geometry with cheaper broad phases

The acceptance order now puts inexpensive rejection first:

1. cached rotation and site AABB bounds;
2. spatial-bucket lookup of nearby placements;
3. exact site containment and positive-area polygon overlap;
4. exact neighbor/shared-wall and strict alignment checks; and
5. cell rasterization only for a surviving candidate.

Placements maintain AABBs, spatial-bucket membership, adjacency, and exposed residual attachment edges incrementally. Attachment edges are indexed by angle. A bounded query takes a rotating stratified view of at most 12 entries instead of permanently favoring one end of a large bucket. Candidate category quotas stop the initial search once enough legal actions exist.

The C ABI combines related traversals, caches value-keyed packed buffers safely, and covers:

- positive-interior polygon overlap, preserving wall/vertex contact as non-overlap;
- site containment that splits candidate edges at every boundary intersection, including concave escape/re-entry cases;
- longest and total shared-wall overlap in one traversal;
- symmetric tolerant segment overlap used by BPE port matching; and
- minimum point-to-segment distance used by wall/daylight metrics.

`tests/test_native_geometry.py` compares native and Python behavior on contact, containment, holes, concavity, length-scaled tolerances, randomized polygons, 1,000 tolerant segment cases, and mutable-input cache safety.

### 2. Bounded parallel placement loop

Active floors generate proposals concurrently through a fixed thread pool, but results are consumed in deterministic floor order. The placement policy scores all legal candidates in one tensor call. On CPU, Torch defaults to one intra-op thread because these batches are too small to amortize a large math thread pool.

Full BPE and layout-graph reconstruction do not influence environment transitions, so they now run only at terminal completion or when the paused UI explicitly requests evaluation. The per-step `bpeMerge` profiler record remains present at zero to make the change visible in telemetry. Terminal BPE remains a measurable cost and is intentionally not hidden.

### 3. Monte Carlo actor–critic

The old terminal REINFORCE-style learner averaged individual action log-probabilities, which gives short and dead-ended trajectories disproportionate weight and retains a high-variance scalar baseline. v0.8.1:

- samples placement actions without retaining a full per-step autograd graph;
- stores bounded candidate feature matrices and selected action indices;
- recomputes placement logits in one differentiable terminal batch;
- sums log-probabilities within each floor trajectory, then averages independent floor trajectories;
- trains a value head against normalized terminal score with smooth L1 loss;
- clips the terminal advantage to `[-1, 1]`;
- adds normalized categorical entropy and clips gradient norm to 2; and
- uses a default learning rate of 0.001, validated within 0.0001–0.05.

This is a Monte Carlo critic, not PPO, TD(n), GAE, or off-policy replay. Exact terminal geometry remains the return source. That is the lowest-risk variance reduction that fixes trajectory weighting without introducing a proxy intermediate value whose relation to the final topology checks has not been validated. Long-horizon convergence stability still needs a larger multi-seed study; the checked-in 10/20-episode runs establish runtime and early behavior, not convergence.

Checkpoint format 5 includes the critic, learner telemetry, bounded reward-reference state, and CPU/available-accelerator RNG state. Loading requires PyTorch 2.6 or newer, uses its restricted weights-only decoder, limits input to 64 MiB, validates tensor/scalar state plus canonical Adam group and moment invariants, and commits transactionally. Saves use atomic temporary-file replacement with partial-file cleanup. Older runtimes fail closed because their weights-only loader is affected by [CVE-2025-32434](https://github.com/pytorch/pytorch/security/advisories/GHSA-53q9-r3pm-6pq6). Format-3 checkpoints can load the actor while initializing a genuinely fresh critic/optimizer; historical learning rates are clamped to the new stable range and marginal 20m² core settings are expanded to the current 24m² feasibility envelope. Format-4 checkpoints remain loadable and reset the reward references they did not store.

### 4. Reward and diagnostics

Elapsed generation time and size-normalized time are reported but are not reward inputs. A faster GPU, a loaded workstation, or a profiler should therefore not change the target solely through wall clock. The relative term rewards deterministic exposed-frontier growth and applies a small-shape exploitation penalty.

Terminal scoring reports raw score and its fill, rentable, daylight, reuse, constructibility, envelope, topology, BPE, triangle, frontier, and dictionary-cap components. BPE reuse is exactly +3 per globally reused occurrence. Repeated paused evaluation is state-pure: it does not advance topology multipliers or reward baselines.

The hidden developer panel (`Ctrl/Cmd+Shift+D`) renders the latest 120 score points, reward bars, native ABI/load state, candidate counts, peak process/accelerator memory, actor/value/entropy/advantage/gradient telemetry, and average/max/count for major profiler phases. It updates only while open to keep UI work bounded.

## Native build and fallback

From `v0.8.1`:

```bash
python3 build_native.py
```

The script uses `CC` when supplied, otherwise finds `cc`, `clang`, or `gcc`; compiles C11 with warnings as errors; emits a macOS `.dylib` or Linux `.so`; loads the temporary output; verifies ABI 3; and only then replaces the installed library. `--debug` uses `-O0 -g`, and `--clean` removes the current platform library.

Import does not require the native library. A missing file, ABI mismatch, load error, unsupported platform, or `MODULE_LAB_DISABLE_NATIVE_GEOMETRY=1` leaves the Python reference active. `native_geometry_status()` exposes availability, enabled state, ABI, selected library, load error, and environment override to the UI.

No macOS, MPS, CUDA, or RTX timing is included in this report. `MODULE_LAB_DEVICE=mps`, `cuda`, and `cuda:N` are device-selection controls, not measured speed-up claims. Proposal generation and vector geometry remain CPU work even when Torch uses an accelerator.

## Graph proposal decision

The recovered raw `FrontierGraph` was evaluated, not merged. At 96 modules its query was 13.6x slower than the current bounded residual-edge query and emitted 79% more anchors. The bounded production view retained 24 of 40 legal actions; the unbounded existing angle index and raw graph both reached all 40, but exact geometry rejected the raw graph's extra internal-edge anchors. The unbounded angle index matched exhaustive residual-edge scanning, demonstrating that the useful graph broad phase already exists in production state.

The evaluation's low-risk follow-up—rotate and stratify the bounded view instead of permanently favoring recent edges—is implemented in v0.8.1. Rebuilding the full layout graph also grew from 0.243 ms at 6 modules to 9.552 ms at 96 modules. This supports terminal-only BPE extraction. Exact benchmark tables, methodology, and the GNN follow-up criteria are in [GRAPH_EVALUATION.md](GRAPH_EVALUATION.md).

## Reproduction commands

Run from `v0.8.1`. These commands write new files so the checked-in evidence remains unchanged.

Final-code lobed run and same-configuration root baseline, 10 measured episodes:

```bash
python3 scratch/benchmark.py \
  --module-dir baseline=.. \
  --module-dir v0.8.1=. \
  --episodes 10 \
  --seed 123 \
  --settings '{"boundaryType":"lobed","atriumPolicy":"agent","parallelEnvironments":4,"maxModules":20,"dictCap":10,"angleStep":15}' \
  --json-out scratch/repro_10ep_lobed_seed123_release.json \
  --csv-out scratch/repro_10ep_lobed_seed123_release.csv
```

Rectangular, one warm-up plus 20 measured episodes:

```bash
python3 scratch/benchmark.py \
  --module-dir baseline=.. \
  --module-dir v0.8.1=. \
  --episodes 20 \
  --warmup 1 \
  --seed 812 \
  --settings '{"boundaryType":"rect","atriumPolicy":"none","parallelEnvironments":4,"maxModules":10,"dictCap":6,"angleStep":90}' \
  --json-out scratch/repro_20ep_rect_seed812.json \
  --csv-out scratch/repro_20ep_rect_seed812.csv
```

Graph-frontier evaluation:

```bash
python3 scratch/benchmark_graph_frontier.py --repetitions 250
python3 -m unittest discover -s tests -p "test_graph_evaluation.py" -v
```

The benchmark's fresh processes are important. Importing the baseline and contender into one interpreter would contaminate `sys.modules`, native-library selection, caches, and Torch runtime state.

## Known limitations and next measurements

- The hard speed numbers cover one CPU host and two settings. Run the same harness on Apple CPU/MPS and on each RTX device before choosing deployment defaults.
- The first 10/20 episodes show early training behavior, not convergence. A multi-seed, fixed-wall-budget learning-curve comparison is still needed for MC actor–critic versus PPO/GAE or TD methods.
- Candidate and shape generation, learning, and terminal BPE remain the largest named costs in the final lobed artifact. Terminal BPE was deferred, not eliminated.
- The bounded 12-edge frontier view trades exhaustive legal-action recall for stable work. Rotation/stratification prevents permanent edge starvation, but a lossless evaluation mode costs more and can expose more placements.
- The lobed workload demonstrates a real composite-score/reuse trade-off. More unique shapes do not automatically mean a better learned vocabulary.
- A single trainer does not distribute one episode across two GPUs. Two `cuda:N` processes are independent experiments.
- In the restricted development sandbox, in-process FastAPI `TestClient` WebSocket tests can block on cross-thread event-loop wakeup. Use a real server process there and rerun `tests/test_websocket.py` on a normal host or CI runner.
- The lobed release artifact measures the final checked-in code. The rectangular paired result and superseded lobed candidates predate later edits and remain historical point-in-time evidence; none justify claims for hardware that was not measured.
