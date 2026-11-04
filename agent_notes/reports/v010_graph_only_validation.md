# v0.10.0 graph-only execution validation — 2026-11-04

Branch `version/v0.10.0`. Training now completes without shared polygon inference, room realization or independent geometry validation. Inference completion and explicit previews realize once per building. Tests assert no geometry calls throughout an actual training episode, a real weight update, and unchanged learner state on preview. Training reports geometry validity as unmeasured (`null`), separately from graph validity.

Final suite: **264 tests in 17.956 seconds, OK (2 skipped)**, including the convex-validator regression. Both the working frontend and an isolated frontend containing only this task's changes build successfully. Unrelated working UI/media/site edits are preserved.

## Measured execution

Raw run: [graph-only training 03](../benchmarks/2026-11-04-v010-graph-only-training-03/). CPU, seed 123, L and XL rectangular sites, four floors, 120 max instances per floor. Both reached 480 floor instances, including vertical copies. Each run performed one real network update.

| Site | Graph training | Separate preview | Median active step | Max active step |
|---|---:|---:|---:|---:|
| L | 8.801 s | 1.688 s | 98.37 ms | 225.27 ms |
| XL | 6.850 s | 1.390 s | 97.44 ms | 232.28 ms |

Setup was 0.074/0.112 seconds. Timings are one-seed diagnostic runs, not peak-throughput, convergence or quality evidence. Before/after cProfile runs used changed trajectories and graph sizes, so no matched speedup ratio is claimed. The before profile's 69 polygon-inference calls per active step are absent from the tested graph-only path. Intermediate runs 01/02 and failed layouts remain saved with their original source snapshots.

Both training runs reported graph access failure and received the fixed invalid graph outcome; previews also failed access. Faster execution does not imply successful architecture generation. Area estimates and provisional module descriptors remain uncalibrated; complementary partial evidence is not yet equivalent to the exact solver.

The original L preview additionally reported an implausible 16.8 m² overlap. The captured footprints lie on opposite sides of a shared bisector; a GEOS overlay robustness failure on nearly coincident endpoints was reproduced. The validator now uses independent SAT on actual convex footprint vertices, without moving or snapping them. Disjoint interiors certify additive measured area; overlapping interiors retain union-area evaluation. The captured-layout `audit_recheck.json` retains the corrected audit alongside the original. Access failures remain failures. This does not broaden the realizer beyond convex modules.

No architecture winner is claimed. Historical architecture pilots used a different geometry-gated reward; pilot 02 was interrupted for this hot-path rewrite. New comparisons must train graph-only, assess held-out realized geometry separately, use identical sites including holes, and retain all failed runs.

## UI and checkpoint follow-up

The live demo performed 41 graph weight updates. Switching to inference kept that count fixed while geometry was realized. A browser-created checkpoint exposed a legacy `siteId` compatibility bug; the fixed loader restores all 41 updates and the original settings. The original default checkpoint was preserved separately from the demo save. Added two checkpoint regressions; **266 tests passed in 16.618 seconds (2 skipped)**. Both isolated release UI and working UI builds pass. Inference now stops on one completed layout for inspection.

Final browser check: the saved network restored 41 updates; graph inference completed with a valid realized layout and stopped automatically without another weight update. Corrected the legacy HUD fallback that substituted -40.0 for numeric score strings, and removed the BPE label from the graph dictionary.
