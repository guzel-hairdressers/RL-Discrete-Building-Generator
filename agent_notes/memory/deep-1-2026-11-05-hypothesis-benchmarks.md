# Deep-1 — 2026-11-05

Branch: version/v0.10.0. Backend worktree: /Users/ruslan_faz/.codex/worktrees/graph-research-v010/Thesis. UI checkout /Users/ruslan_faz/Desktop/Work/Thesis stays on codex/ui-overhaul; its local changes were not edited. No push.

Completed all individual hypothesis pilots and separate L/XL120max/floor4/8-floor measurements, frozen realizers/circulation, alternatives and urban supplement. Read ../reports/v010_hypotheses_benchmarks.md for measured results/raw links. All raw data/failures/source snapshots/checkpoints retained. Experimental checkpoints do not replace production weights.

User screenshot exposed unplanned holes. Baseline original geometry passes69/72 but geometry-plus-enclosed-gap passes0/72. Added independent spatialQuality diagnostics on realization only. Geometry itself is NOT fixed; graph training has no gap-avoidance criterion. No individual shape stretching/fake filler/courtyard relabeling. Next priority: shared contact-endpoint/interior-junction closure and explicit planned voids, benchmarked before adding per-step work.

Corrected graph denominator from raster counts to exact net polygon area, unified building fill ratio-of-sums and benchmark helpers, retained old raw mean-floor statistics. Corrected experimental repair acceptance to exact mean per-floor objective. Authoritative live endgame12cases/72trials cost0.213s mean/six trials,0 accepted,zero fill gain. Earlier export-replay failures remain labeled diagnostics.

310 unit tests completed,2 skipped; native C built. No new UI build needed: backend changes additive, UI work separate. API contract/handoff updated with exact fill and gap semantics. Existing user demo servers were not restarted; they may still run earlier code until integration/restart.
