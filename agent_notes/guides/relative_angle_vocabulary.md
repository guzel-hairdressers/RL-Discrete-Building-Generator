# Relative-angle/length vocabulary and learned exploration

2026-11-05, version/v0.10.0. Implementation: src/relative_vocabulary.py, graph_dictionary.py and graph_policy.py.

For incident bearings theta_i, store phi_ij=(theta_j−theta_i) mod 2pi. All ordered pairs include composite turns: phi_ik=(phi_ij+phi_jk) mod 2pi. Edge lengths and turns are measured from committed graph relationships. The vocabulary is per building and resets with a new layout; held-out evaluation does not leak a global palette into later training.

Keys use eight decimal places for numerical matching, while stored values retain measured precision. Placements are not snapped to degree increments, integer lengths or fixed bays. The size prior still has 64 directions, which can affect inferred perimeter shapes. It is a modeling approximation, not an angle-step restriction.

The three explicit graphProposalStrategy values are legacy (default), continuous and vocabulary. All retain common module-contact proposals. Continuous exploration uses learned relative angles and lengths. Vocabulary adds observed angle/length combinations and mixed routes: new angle with observed length, observed angle with new length, and both new. The final actor chooses among constraint-compatible placements. Bounds derive from minimum separation and twice the configured radius, currently 2.5–9 m at defaults.

The head is conditioned on graph/anchor embeddings and vocabulary counts. Its angle transform is pi*tanh(z_angle); length uses a sigmoid over the feasible range. REINFORCE records the proposal draw and subsequent categorical choice. Reused factors receive no density credit; transformed entropy includes the physical-coordinate Jacobian. GNN encoding is reused between proposal generation and selection for the unchanged graph.

Schema-3 checkpoints add the new head and two proposal-source features. Schema-1/2 migration preserves the old actor/encoder/critic and Adam moments, zero-pads new actor inputs, initializes the head and restores the isolated RNG. Existing weights remain loadable, but their old training quality is not assumed after objective/solver changes.

Shared prototypes remain rotation-only, with target 10 and a hard ceiling of 15. No incompatible merge is allowed. All floors of a full-height occurrence use one shape. Numerical face deduplication and contact aliasing match the independent physical oracle; active prior inequalities are cached only when redundancy is monotone under added cuts.

The [measured comparison](../reports/v010_angle_proposal_evaluation.md) shows a small, uncertain fill advantage for vocabulary proposals and no demonstrated faster learning. Both experimental strategies remain opt-in. No 90-degree preference, corridor policy or pose-repair learner has been implemented by this change.
