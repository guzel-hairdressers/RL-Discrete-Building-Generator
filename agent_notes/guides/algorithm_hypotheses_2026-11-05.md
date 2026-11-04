# Next algorithm experiments — 2026-11-05

These are hypotheses and proposed tests, not implemented improvements or performance claims. Keep graph inference and physical validation separate. The latest [proposal comparison](../reports/v010_angle_proposal_evaluation.md) does not establish faster learning from the angle vocabulary.

## What to optimize

Require valid geometry/access and the intended residential program. Make useful filled area the primary spatial outcome; show residential area and circulation area separately. Keep module reuse, fabrication complexity and right-angle preference visible. Faster termination with lower fill is a regression. Do not reward room count, angle variety, or additional module types for their own sake.

Current settings retain a soft target of 10 types and a ceiling of 15. Spend types 11–15 when their spatial benefit justifies their cost. If no good layout fits that ceiling, report the unresolved tradeoff; do not force incompatible modules into one type. A future budget-conditioned policy should expose measured fill/reuse alternatives rather than silently changing the objective.

## Prioritized hypotheses

| Priority | Hypothesis and evidence | Experiment and adoption check |
|---|---|---|
| 1 | **Give the actor and critic the boundary and the optimization goal.** The current continuous head receives graph/anchor embeddings and vocabulary counts; the critic receives pooled graph features. Neither directly receives the site boundary or the user's budget/preference vector. | Add nearby boundary segments, corners, holes and local clearance in an intrinsic frame, plus site area, budget and preference inputs. Compare equal-compute models on held-out oblique, acute, concave and courtyard plots. Require better validated fill and learning curves, not just a lower training loss. |
| 2 | **Learn to rank proposals before expensive exact checks.** Current action selection largely happens after compatible plans have already been computed. | Use cheap local features to order candidates, validate a small adaptive subset, expand if needed. Collect feasibility labels from the exact constraint checker. Never accept a candidate solely because a network predicts it valid. Measure checks/accepted placement, missed opportunities, fill and p95 latency. |
| 3 | **Permit local repair instead of irreversible growth.** New nodes can refine shared shapes, but the policy does not automatically reposition old occurrences or revisit old assignments. | Add bounded transactional move/rotate/reassign operations around underfilled regions. Revalidate every affected occurrence of a changed prototype and all full-height references. Compare under the same wall-time budget. |
| 4 | **Prefer right-angle module corners softly, without imposing a global lattice.** Graph-edge angles and polygon corners are different objects. | Score actual adjacent active prototype facets, in a free local orientation. Use a robust cost around 90 degrees, merge collinear facets and handle prior-derived boundaries explicitly. Keep a continuous proposal route. Hold fill/access/program requirements ahead of this preference. |
| 5 | **Plan circulation explicitly.** Current occupied-room reachability does not by itself encode private/public access, apartment grouping or deliberate corridor layouts. | Introduce circulation and unit membership, explicit usable openings, and short action sequences such as corridor growth followed by room attachments. Count corridor area and impose the chosen residential program so an all-corridor floor cannot win. Test access distance, bottlenecks, residential fill and reuse. |
| 6 | **Test a contact-port realizer against the Voronoi adapter.** Midpoint bisectors tightly couple origin positions, wall normals and cell size. | Let an edge identify a contact interval/port in each module's frame. Pool boundary evidence across occurrences, preserving exact shared geometry. This needs spatial separation certificates for non-neighbors; it must not pretend that overlap checks become unnecessary. Start with small correctness cases and then the official L/XL workload. |
| 7 | **Use more precise cheap site certificates.** The current radius-clearance check is conservative, especially for small or perimeter occurrences. | Test prototype-specific support/radius certificates and local boundary indexing. Keep concavities and holes intact; vertex-inside tests alone are insufficient for concave sites. Check that gains come from valid perimeter coverage, not clipping or deformation. |
| 8 | **Retain different good layouts rather than reward visual complexity.** Diversity is useful for alternatives but can conflict with reuse if it is paid for directly. | Maintain an archive of comparable-quality solutions with different circulation/contact topology and boundary adaptation. Rectilinear layouts remain legitimate where they work. Require adaptation where a uniform grid loses fill or access quality. |

## Ninety-degree corners without rectangular-grid dependence

For the current midpoint adapter, a displacement d gives an outward boundary normal parallel to d. If two *consecutive active* outward normals turn through delta, their convex interior corner is pi − delta. A 90-degree relation between arbitrary incident graph edges is therefore not a reliable corner reward: some edges correspond to nonconsecutive or inactive boundaries.

Do not use a naive periodic angle bonus that also rewards zero/180-degree degeneracies. Do not pay an orthogonality bonus for artificial faces supplied by the 64-direction size prior. Unobserved boundaries need explicit uncertainty treatment, not an opportunity to avoid costs by withholding evidence.

There is a real geometric tradeoff: if every convex module has only 90-degree corners, it is rectangular. Positive-length wall contacts then tend to lock connected rectangles to common axes. Those axes need not be world axes, and dimensions need not lie on a grid, but arbitrary oblique boundaries still need gaps or nonrectangular transition/perimeter modules. The promising hypothesis is repeated, mostly orthogonal interior modules plus a small number of justified boundary types—not mandatory rectangles everywhere.

Train the policy across a mixture of plot shapes, rotations and scales, with budgets and preferences supplied as inputs. Retain difficult plots throughout training; a curriculum must not end up teaching only rectangular sites. Goal-conditioned value functions are an established approach, but their benefit here remains to be tested: [Schaul et al., 2015](https://proceedings.mlr.press/v37/schaul15.html).

## Circulation and the diagonal issue

Corner contact does not provide a usable doorway. Adding a diagonal access edge without a shared opening would falsify accessibility. A corridor can be a chain or group of reusable convex occurrences, with one circulation network serving multiple units. A functional space need not be confused with one manufacturing module. Private-unit traversal and public circulation should be separate relations.

One limitation follows from ordinary point Voronoi geometry: distinct neighbors normally meet a cell on different bisectors. It is restrictive for one long straight corridor wall to serve several separately positioned rooms along that same wall. This is a deduction from the nearest-site/bisector construction, not a benchmark result. See [CGAL's definition](https://doc.cgal.org/latest/Voronoi_diagram_2/index.html).

Power diagrams can loosen area/offset coupling through weights, but retain origin-dependent bisector normals. They are worth an adapter experiment, not a guaranteed corridor solution. [CGAL regular triangulations](https://doc.cgal.org/latest/Triangulation_2/index.html#secRegularTriangulation) describe the weighted construction. Contact ports or grouped convex pieces address a different modeling limitation.

## Efficiency and learning safeguards

Profile the current implementation. Recent profiles place proposal checking, shared-shape updates and graph encoding above final geometry during training. Global contact preservation was not the dominant cost in the sampled step; do not optimize it on assumption alone.

Reuse cached prototype features, active half-spaces and local neighborhoods. Incremental GNN updates require care: the current centroid-relative node features change globally after an insertion. Use local relative features plus explicit global summaries if incrementality is the goal. Preserve handedness; reflection-invariant embeddings alone cannot distinguish mirrored asymmetric modules when equivalence permits rotation only.

Potential-based shaping may improve credit assignment while retaining the chosen final objective. With undiscounted finite episodes, terminal potential must be handled consistently. Never add an unbounded reward for adding nodes, reusing an angle or delaying failure. [Ng, Harada and Russell, 1999](https://ai.stanford.edu/~ang/papers/shaping-icml99.pdf) establish the relevant policy-invariance conditions.

Test parallel *buildings*, each with its own dictionary, rather than treating floors sharing a dictionary as independent environments. Measure throughput, per-episode latency and memory; extra workers are not automatically faster on a memory-constrained desktop.

Use one change per ablation. Quality: ANY/FREE, changing sites, multiple seeds and frozen independent geometry evaluation. Speed: L/XL, 120 max/floor, 4 and 8 floors, with actual reached sizes. Keep failed runs and report both episode-count and wall-time learning curves. No new default should be justified by a faster but less-filled layout.
