# UI/UX overhaul handoff — 2026-11-05

## Task to give the UI agent

Redesign the existing Module Lab UI to make model behavior, architectural results and uncertainty understandable with fewer competing controls. Preserve the functional graph training/inference workflow and the current site's visual context. This is a repository UI overhaul, not a new hosted site.

Use the original checkout `/Users/ruslan_faz/Desktop/Work/Thesis`, reserved branch `codex/ui-overhaul`. The backend agent works in `/Users/ruslan_faz/.codex/worktrees/graph-research-v010/Thesis` on `version/v0.10.0`. Verify the branch before editing. Do not create a new chat/agent on behalf of the user.

Read [the API contract](../contracts/graph_ui_v010.md), [the measured experiment](../reports/v010_angle_proposal_evaluation.md) and the current source before designing. The new angle vocabulary is experimental; faster learning is not established.

## Ownership and existing work

You own frontend source/styles/components and the UI adapter in frontend/src/store/useStore.js. You may edit frontend/public/scripts/urban_viewer.js and its public/scripts compatibility copy for rendering. Keep those source copies synchronized. Put UI notes in a new report file rather than editing shared backend notes.

Do not modify src/, backend tests/tools, the scoring/validity rules, benchmark data, source datasets, checkpoint weights, or custom-site records. Do not add invented backend commands or computed metrics to make the design look complete.

The original checkout already has uncommitted UI changes, README/note changes, custom-site data edits/deletions, generated assets and docs. Preserve them. Inspect them before work; make a clearly scoped UI baseline commit on the UI branch if needed. Do not reset/clean/stash everything or use git add -A. Do not commit unrelated README, site data or benchmark files.

Develop with Vite on port 3000 against the dedicated stable backend at port 8001:

```bash
cd /Users/ruslan_faz/Desktop/Work/Thesis/frontend
MODULE_LAB_BACKEND_URL=http://127.0.0.1:8001 npm run dev -- --port 3000 --strictPort
```

The original server at 8000 remains separate. Backend experiments use headless runs or port 8002; coordinate before changing proxy targets. Keep inference tests separate from training sessions. Run heavy UI rendering/builds outside announced throughput timing windows.

## Recommended information hierarchy

1. **One action bar:** Train / Pause, Generate one layout, then a compact checkpoint menu. Distinguish Reset weights from Fit view. Show mode and current run status.
2. **One primary workspace:** floor plan with floor selection; optional 3D and graph/access layers. Preserve camera/zoom while data changes. 3D can be off during training for speed.
3. **A few honest outcomes:** filled area and fill fraction, residential area, independent reuse, module types (10 target / 15 max), and access/geometry status. Label graph estimates versus verified results clearly.
4. **A module palette:** stable module colors/IDs; select a type to highlight its occurrences. Show independent uses separately from vertical copies. During graph-only training, show metadata without fake/empty polygon thumbnails. Shape/function are separate.
5. **Progressive detail:** configuration drawer, performance/learning diagnostics, and a selected-occurrence inspector. Do not put every research metric on the main canvas.

All-node text badges currently overwhelm dense views. Prefer colors/hover/selection, with labels at useful zoom levels. Make construction, physical contact and usable access distinguishable. A diagonal/corner touch is not a valid door connection.

Default plots should answer whether fill/reuse and validity improve, not merely whether a loss changes. Preserve failed runs and distinguish training estimates from occasional realized checks. Show wall time, server runtime and validation time as different quantities.

Scope settings to the active engine: legacy 45-degree crevice labels and C-collision claims should not imply that graph angles are restricted. Keep advanced proposal/controller options accessible but secondary. Do not ship a nonfunctional 90-degree preference slider; that backend experiment is still proposed.

## Interaction and implementation checks

- Training advances without a render/timer gate; batches are not individual room placements.
- Pause handles late messages and previews without another optimizer update.
- Graph inference stops after one completed layout.
- Settings updates consume authoritative server settings and reject stale generations.
- Save/load/reset remain functional, including historical checkpoint migration.
- Missing daylight/environmental metrics remain unmeasured, not zero-percent results.
- No repeated iframe setup, per-node texture creation, camera resets or full urban-scene traversal on every graph message.
- Verify narrow and wide layouts, keyboard controls, readable contrast and dense multi-floor views. Include screenshots of the working result and a concise interaction report.

Build/test what you change. State-machine or protocol changes warrant behavioral checks; cosmetic changes do not need mirror-image unit tests. Keep generated frontend/dist out of source commits: the integration agent will rebuild it once from merged sources, preserving custom-site data.

## Delivery and merge

Commit UI source on codex/ui-overhaul. Report commit IDs, changed files, build/interaction checks, screenshots and any requested API additions. Do not merge the backend branch, alter the release branch, or push remotely.

The backend agent will review the diff, merge the UI branch into version/v0.10.0, resolve protocol conflicts, rebuild assets once, and run combined verification. Worktrees isolate edits; integration tests still decide whether the combined result is correct.
