# Graph frontier evaluation

## Decision

Do **not** integrate the recovered `FrontierGraph` or create graph variants of
v0.8.0/v0.8.1 yet. The production environment already has the useful graph
structure: an incremental module adjacency map, exact exposed residual edges,
an angle index over those edges, and a spatial index for nearby polygons. The
recovered prototype duplicates that state, retains covered/internal edges, and
is slower once authoritative geometry rejection is included.

Keep vector geometry authoritative. If more placement diversity is wanted,
change how the existing angle-indexed residual edges are sampled; a second
frontier graph is not needed.

## What was compared

`scratch/benchmark_graph_frontier.py` compares four providers while holding the
module, rotation, site, and exact acceptance checks constant:

1. **Current bounded** — the production residual-edge/angle index with
   `ATTACHMENT_MATCH_LIMIT=12`.
2. **Exact indexed** — the same graph and index with no per-angle cap.
3. **Exhaustive residual** — every exact exposed residual edge, used as the
   parity oracle.
4. **Proposed raw graph** — the endpoint-only `FrontierGraph` recovered from
   upstream commit `9087b55`; its original edges are never split or retired.

An action is identified by its unique translation. Every reported legal action
passed site containment, polygon overlap, neighbor/contact, strict edge-ratio,
and raster/site-cell checks. The run used 250 timed repetitions on an Intel Core
Ultra 9 285K, Python 3.10.18, with native geometry ABI 3 enabled.

Reproduce it with:

```bash
python3 scratch/benchmark_graph_frontier.py --repetitions 250
python3 -m unittest -v tests.test_graph_evaluation
```

## Results

The unbounded angle index matched the exhaustive residual scan exactly in all
three deterministic layouts and both policy rollouts. It is therefore a
lossless broad phase. The graph does not make the downstream vector checks
optional.

| Layout | Residual/raw edges | Current / exact / raw anchors | Current legal recall | Raw anchor precision | Query median (current / exact / raw) | Full layout-graph rebuild |
|---|---:|---:|---:|---:|---:|---:|
| Compact 6 | 10 / 24 | 16 / 16 / 16 | 100% | 100% | 12.5 / 13.7 / 23.1 us | 0.243 ms |
| Compact 48 | 28 / 192 | 45 / 52 / 76 | 85.7% | 68.4% | 25.3 / 32.3 / 180.7 us | 3.965 ms |
| Compact 96 | 40 / 384 | 46 / 76 / 136 | 60.0% | 55.9% | 26.8 / 43.6 / 366.0 us | 9.552 ms |
| Policy rollout, seed 812 (10 modules) | 10 / 40 | 10 / 10 / 27 | 100% | 37.0% | 7.9 / 8.2 / 36.2 us | 0.529 ms |
| Policy rollout, seed 1881 (10 modules) | 12 / 33 | 13 / 13 / 10 | 100% | 60.0% | 6.1 / 6.3 / 21.0 us | 0.399 ms |

On the 96-module layout, the proposed raw graph query was 13.6x slower than the
current query and produced 79% more unique anchors than the exact residual
graph. Those extras were rejected by geometry. End-to-end legal filtering took
2.434 ms with the current cap, 4.009 ms with the lossless index, and 5.439 ms
with the proposed raw graph. The raw graph recovered the same 40 legal actions
only after paying for its internal-edge rejects.

The full `graph.extract_layout_graph` rebuild scaled from 0.243 ms at 6 modules
to 9.552 ms at 96 modules. That supports keeping adjacency/BPE graph extraction
at pause or episode completion rather than rebuilding it during placement.

## Diversity finding

The production cap is intentionally **not** lossless. On compact 48- and
96-module layouts it retained 24 of 28 and 24 of 40 legal transforms,
respectively. This is a bounded-work choice, not a property of graph
representation. Candidate selection needs at most 12 returned actions, so even
the capped cases retained twice that number for the square probe, but always
favoring recent/preferred edges can narrow spatial diversity over time.

v0.8.1 implements the lowest-risk follow-up: a deterministic rotating,
stratified sample of the existing angle bucket. It preserves bounded work while
preventing the same newest 12 edges from monopolizing every query. If a strict
lossless mode is desired for evaluation, make the match cap optional; the
96-module probe measured a 1.65x legal-filter cost (2.434 to 4.009 ms) for 40
instead of 24 legal transforms.

## Why a geometry-free graph is insufficient

The proposal suggests that ports can omit edge lengths and internal angles.
That representation cannot decide site containment, atrium intersection,
non-neighbor collision, exact shared-wall ratios, daylight distance, or the
world-space transform of a candidate. Topologically identical graphs can have
different legal actions when translated near a site boundary or when their
edge metrics differ. Exact geometry therefore remains required even if a GNN
later consumes topology features.

A GNN may still be worth a separate sample-efficiency experiment, but it is not
a demonstrated speed optimization. Such an experiment should consume the
already-maintained `adjacency_map` and residual-edge features, compare fixed
seed learning curves and wall time against the current pooled encoder, and be
accepted only if quality/sample efficiency improves enough to pay for message
passing. No graph-policy code was integrated in v0.8.1 because that evidence is
not present.
