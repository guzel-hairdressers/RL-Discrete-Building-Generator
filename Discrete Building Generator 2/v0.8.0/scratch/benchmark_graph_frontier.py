#!/usr/bin/env python3
"""Measure graph-frontier proposal parity and cost without changing the trainer.

The benchmark compares four anchor providers:

``current_bounded``
    The production residual-edge/angle index, including its per-angle cap.
``exact_indexed``
    The same residual-edge graph and angle index without the cap.  This is the
    lossless graph broad phase used as the action-set reference.
``exhaustive_residual``
    A scan of every residual edge.  It is deliberately slow and serves as the
    parity oracle for ``exact_indexed``.
``proposed_raw_graph``
    The endpoint-only, never-retired FrontierGraph proposal recovered from the
    upstream feature branch.  It is reproduced here rather than integrated.

Run from the v0.8.0 or v0.8.1 directory (or anywhere else):

    python3 scratch/benchmark_graph_frontier.py --repetitions 250

The result is JSON on stdout so it can be archived by a caller if desired.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import statistics
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from typing import Any


MODULE_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

import geometry as G  # noqa: E402
import graph  # noqa: E402
import server  # noqa: E402


Anchor = tuple[float, float, int | None]


def _edge_anchors(
    environment: server.FloorEnvironment,
    candidate_first: dict[str, float],
    candidate_second: dict[str, float],
    edge: dict[str, Any],
) -> list[Anchor]:
    """Return the production endpoint/center anchors for one parallel edge."""

    candidate_dx = candidate_second["x"] - candidate_first["x"]
    candidate_dy = candidate_second["y"] - candidate_first["y"]
    candidate_length = math.hypot(candidate_dx, candidate_dy)
    if candidate_length < server.MIN_SHARED_EDGE:
        return []

    placed_first = edge["a"]
    placed_second = edge["b"]
    placed_dx = placed_second["x"] - placed_first["x"]
    placed_dy = placed_second["y"] - placed_first["y"]
    placed_length = float(edge["length"])
    placed_poly = environment.placement_by_id[edge["placementId"]]["poly"]
    full_first = placed_poly[edge["edgeIndex"]]
    full_second = placed_poly[(edge["edgeIndex"] + 1) % len(placed_poly)]
    full_placed_length = math.hypot(
        full_second["x"] - full_first["x"],
        full_second["y"] - full_first["y"],
    )
    length_ratio = candidate_length / max(full_placed_length, G.EPSILON)
    if not any(
        abs(length_ratio - valid_ratio) < 5.0e-3
        for valid_ratio in (0.5, 1.0, 2.0)
    ):
        return []
    cross = placed_dx * candidate_dy - placed_dy * candidate_dx
    if abs(cross) > 1.0e-7 * placed_length * candidate_length:
        return []

    edge_id = edge.get("id")
    if placed_dx * candidate_dx + placed_dy * candidate_dy < 0.0:
        anchors: list[Anchor] = [
            (
                placed_second["x"] - candidate_first["x"],
                placed_second["y"] - candidate_first["y"],
                edge_id,
            ),
            (
                placed_first["x"] - candidate_second["x"],
                placed_first["y"] - candidate_second["y"],
                edge_id,
            ),
        ]
    else:
        anchors = [
            (
                placed_first["x"] - candidate_first["x"],
                placed_first["y"] - candidate_first["y"],
                edge_id,
            ),
            (
                placed_second["x"] - candidate_second["x"],
                placed_second["y"] - candidate_second["y"],
                edge_id,
            ),
        ]
    anchors.append(
        (
            (
                placed_first["x"]
                + placed_second["x"]
                - candidate_first["x"]
                - candidate_second["x"]
            )
            * 0.5,
            (
                placed_first["y"]
                + placed_second["y"]
                - candidate_first["y"]
                - candidate_second["y"]
            )
            * 0.5,
            edge_id,
        )
    )
    return anchors


def exhaustive_residual_anchors(
    environment: server.FloorEnvironment,
    rotation: dict[str, Any],
) -> list[Anchor]:
    """Scan every exact exposed residual edge (the parity oracle)."""

    anchors: list[Anchor] = []
    candidate_poly = rotation["poly"]
    for index, candidate_first in enumerate(candidate_poly):
        candidate_second = candidate_poly[(index + 1) % len(candidate_poly)]
        for edge in environment.attachment_edges.values():
            anchors.extend(
                _edge_anchors(
                    environment, candidate_first, candidate_second, edge
                )
            )
    return anchors


def exact_indexed_anchors(
    environment: server.FloorEnvironment,
    rotation: dict[str, Any],
) -> list[Anchor]:
    """Query the production angle index without its intentionally lossy cap."""

    anchors: list[Anchor] = []
    candidate_poly = rotation["poly"]
    angle_period = int(round(math.pi * server.ATTACHMENT_ANGLE_SCALE))
    for index, candidate_first in enumerate(candidate_poly):
        candidate_second = candidate_poly[(index + 1) % len(candidate_poly)]
        if math.hypot(
            candidate_second["x"] - candidate_first["x"],
            candidate_second["y"] - candidate_first["y"],
        ) < server.MIN_SHARED_EDGE:
            continue
        angle_key = environment._attachment_angle_key(candidate_first, candidate_second)
        edge_ids: set[int] = set()
        for delta in (-2, -1, 0, 1, 2):
            lookup = (angle_key + delta) % angle_period
            edge_ids.update(environment.attachment_by_angle.get(lookup, ()))
        for edge_id in edge_ids:
            edge = environment.attachment_edges.get(edge_id)
            if edge is not None:
                anchors.extend(
                    _edge_anchors(
                        environment, candidate_first, candidate_second, edge
                    )
                )
    return anchors


def current_bounded_anchors(
    environment: server.FloorEnvironment,
    rotation: dict[str, Any],
) -> list[Anchor]:
    """Expose the exact anchor triples generated by the production method."""

    return list(environment._edge_alignment_anchors({}, rotation, include_edge_id=True))


def proposed_raw_graph_anchors(
    environment: server.FloorEnvironment,
    rotation: dict[str, Any],
) -> list[Anchor]:
    """Reproduce the recovered feature-branch FrontierGraph query.

    Its graph retains every original placement edge forever, uses a broad
    normal-dot threshold, and emits endpoint alignments only.  Covered/internal
    edges therefore survive as proposal sources and still require the complete
    vector rejection path.
    """

    anchors: list[Anchor] = []
    candidate_poly = rotation["poly"]
    for candidate_index, candidate_first in enumerate(candidate_poly):
        candidate_second = candidate_poly[(candidate_index + 1) % len(candidate_poly)]
        candidate_dx = candidate_second["x"] - candidate_first["x"]
        candidate_dy = candidate_second["y"] - candidate_first["y"]
        candidate_length = math.hypot(candidate_dx, candidate_dy)
        if candidate_length < server.MIN_SHARED_EDGE:
            continue
        candidate_normal = (-candidate_dy / candidate_length, candidate_dx / candidate_length)
        raw_edge_id = 0
        for placement in environment.placements:
            placed_poly = placement["poly"]
            for placed_index, placed_first in enumerate(placed_poly):
                placed_second = placed_poly[(placed_index + 1) % len(placed_poly)]
                placed_dx = placed_second["x"] - placed_first["x"]
                placed_dy = placed_second["y"] - placed_first["y"]
                placed_length = math.hypot(placed_dx, placed_dy)
                raw_edge_id += 1
                if placed_length < server.MIN_SHARED_EDGE:
                    continue
                placed_normal = (-placed_dy / placed_length, placed_dx / placed_length)
                normal_dot = (
                    candidate_normal[0] * placed_normal[0]
                    + candidate_normal[1] * placed_normal[1]
                )
                if normal_dot > -0.99:
                    continue
                anchors.append(
                    (
                        placed_second["x"] - candidate_first["x"],
                        placed_second["y"] - candidate_first["y"],
                        raw_edge_id,
                    )
                )
                anchors.append(
                    (
                        placed_first["x"] - candidate_second["x"],
                        placed_first["y"] - candidate_second["y"],
                        raw_edge_id,
                    )
                )
    return anchors


def anchor_signatures(anchors: Iterable[Anchor]) -> set[tuple[float, float]]:
    """Collapse edge provenance because an action is a unique transform."""

    return {(round(float(x), 6), round(float(y), 6)) for x, y, _ in anchors}


def legal_action_signatures(
    environment: server.FloorEnvironment,
    module: dict[str, Any],
    rotation: dict[str, Any],
    anchors: Iterable[Anchor],
) -> set[tuple[float, float]]:
    """Run the authoritative vector, alignment, and raster acceptance path."""

    settings = dict(server.DEFAULT_SETTINGS)
    settings["singleFloor"] = True
    result: set[tuple[float, float]] = set()
    for anchor_x, anchor_y in anchor_signatures(anchors):
        candidate = environment._candidate_from_anchor(
            module,
            rotation,
            anchor_x,
            anchor_y,
            settings,
            0.0,
            {},
            placement_category="room",
        )
        if candidate is None or not environment._validate_edge_alignment(candidate.poly):
            continue
        if not environment._materialize_candidate(candidate, settings, 0.0):
            continue
        result.add((anchor_x, anchor_y))
    return result


def make_grid_environment(
    columns: int,
    rows: int,
    cell_size: float = 2.0,
) -> tuple[server.FloorEnvironment, float]:
    """Build a compact connected floor and return frontier maintenance time."""

    boundary = G.make_boundary(
        "rect",
        901,
        {"boundaryWidth": 48.0, "boundaryHeight": 32.0},
    )
    site = G.build_site(boundary, [])
    environment = server.FloorEnvironment(
        0,
        boundary,
        {"id": "none", "holes": []},
        site,
        (0.0, 0.0),
        G.RNG(901),
    )

    start = time.perf_counter()
    for row in range(rows):
        for column in range(columns):
            x = 2.0 + column * cell_size
            y = 2.0 + row * cell_size
            identifier = f"grid-{column}-{row}"
            poly = [
                {"x": x, "y": y},
                {"x": x + cell_size, "y": y},
                {"x": x + cell_size, "y": y + cell_size},
                {"x": x, "y": y + cell_size},
            ]
            placement = {
                "id": identifier,
                "moduleId": "grid-square",
                "category": "room",
                "poly": poly,
                "center": {"x": x + cell_size * 0.5, "y": y + cell_size * 0.5},
                "area": cell_size * cell_size,
                "rotation": 0.0,
            }
            environment.placements.append(placement)
            environment.placement_by_id[identifier] = placement
            environment.adjacency_map[identifier] = set()
            environment._index_placement(placement)
            environment._update_attachment_frontier(placement, {}, [])
            for raster_cell in G.rasterize_polygon(poly):
                environment.occupied[G.key(raster_cell["x"], raster_cell["y"])] = identifier
            environment.filled_area += cell_size * cell_size
            environment.rentable_area += cell_size * cell_size
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return environment, elapsed_ms


def square_probe(cell_size: float = 2.0) -> tuple[dict[str, Any], dict[str, Any]]:
    poly = [
        {"x": 0.0, "y": 0.0},
        {"x": cell_size, "y": 0.0},
        {"x": cell_size, "y": cell_size},
        {"x": 0.0, "y": cell_size},
    ]
    module = {
        "id": "graph-evaluation-probe",
        "category": "room",
        "area": cell_size * cell_size,
        "regularity": 1.0,
        "minWidth": cell_size,
        "triangle": False,
    }
    rotation = {"angle": 0.0, "poly": poly, "bounds": G.bounds_of(poly)}
    return module, rotation


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
    return float(ordered[index])


def timing_summary(function: Callable[[], Any], repetitions: int) -> dict[str, float]:
    for _ in range(min(8, repetitions)):
        function()
    samples: list[float] = []
    for _ in range(repetitions):
        start = time.perf_counter_ns()
        function()
        samples.append((time.perf_counter_ns() - start) / 1000.0)
    return {
        "median_us": round(statistics.median(samples), 3),
        "p95_us": round(_percentile(samples, 0.95), 3),
    }


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 1.0


def evaluate_scenario(
    name: str,
    environment: server.FloorEnvironment,
    module: dict[str, Any],
    rotation: dict[str, Any],
    repetitions: int,
    build_ms: float = 0.0,
) -> dict[str, Any]:
    providers: dict[str, Callable[[], list[Anchor]]] = {
        "current_bounded": lambda: current_bounded_anchors(environment, rotation),
        "exact_indexed": lambda: exact_indexed_anchors(environment, rotation),
        "exhaustive_residual": lambda: exhaustive_residual_anchors(environment, rotation),
        "proposed_raw_graph": lambda: proposed_raw_graph_anchors(environment, rotation),
    }
    anchors = {provider: function() for provider, function in providers.items()}
    anchor_sets = {provider: anchor_signatures(items) for provider, items in anchors.items()}
    legal_sets = {
        provider: legal_action_signatures(environment, module, rotation, items)
        for provider, items in anchors.items()
    }

    exact = anchor_sets["exact_indexed"]
    exhaustive = anchor_sets["exhaustive_residual"]
    if exact != exhaustive:
        raise AssertionError(
            f"lossless angle index diverged from exhaustive residual scan in {name}"
        )
    exact_legal = legal_sets["exact_indexed"]
    if exact_legal != legal_sets["exhaustive_residual"]:
        raise AssertionError(
            f"lossless angle index changed legal actions in {name}"
        )

    query_repetitions = max(10, repetitions)
    end_to_end_repetitions = max(3, min(12, repetitions // 20))
    graph_repetitions = max(3, min(20, repetitions // 15))
    query_timings = {
        provider: timing_summary(function, query_repetitions)
        for provider, function in providers.items()
    }
    end_to_end_timings = {
        provider: timing_summary(
            lambda function=function: legal_action_signatures(
                environment, module, rotation, function()
            ),
            end_to_end_repetitions,
        )
        for provider, function in providers.items()
    }
    extracted = graph.extract_layout_graph(environment.placements, environment.index)
    graph_rebuild_timing = timing_summary(
        lambda: graph.extract_layout_graph(environment.placements, environment.index),
        graph_repetitions,
    )

    current = anchor_sets["current_bounded"]
    current_legal = legal_sets["current_bounded"]
    raw = anchor_sets["proposed_raw_graph"]
    raw_legal = legal_sets["proposed_raw_graph"]
    return {
        "name": name,
        "placements": len(environment.placements),
        "residual_frontier_edges": len(environment.attachment_edges),
        "raw_graph_edges": sum(len(item["poly"]) for item in environment.placements),
        "incremental_frontier_build_ms": round(build_ms, 3),
        "anchor_counts": {key: len(value) for key, value in anchor_sets.items()},
        "legal_action_counts": {key: len(value) for key, value in legal_sets.items()},
        "exact_index_matches_exhaustive": True,
        "current_anchor_recall": _ratio(len(current & exact), len(exact)),
        "current_legal_action_recall": _ratio(
            len(current_legal & exact_legal), len(exact_legal)
        ),
        "proposed_raw_anchor_precision": _ratio(len(raw & exact), len(raw)),
        "proposed_raw_anchor_recall": _ratio(len(raw & exact), len(exact)),
        "proposed_raw_legal_action_precision": _ratio(
            len(raw_legal & exact_legal), len(raw_legal)
        ),
        "proposed_raw_legal_action_recall": _ratio(
            len(raw_legal & exact_legal), len(exact_legal)
        ),
        "query_timing": query_timings,
        "legal_filter_timing": end_to_end_timings,
        "layout_graph_rebuild": {
            **graph_rebuild_timing,
            "connections": len(extracted.connections),
        },
    }


def rollout_environment(
    seed: int,
    target_placements: int = 10,
) -> tuple[server.FloorEnvironment, dict[str, Any], dict[str, Any]]:
    """Create one real policy rollout and select its richest probe rotation."""

    import torch

    torch.manual_seed(seed)
    trainer = server.ParallelTrainer()
    trainer.update_settings(
        {
            "boundaryType": "rect",
            "atriumPolicy": "none",
            "singleFloor": True,
            "parallelEnvironments": 1,
            "maxModules": max(14, target_placements + 2),
            "dictCap": 6,
            "angleStep": 90.0,
            "seed": seed,
        }
    )
    environment = trainer.environments[0]
    for _ in range(max(30, target_placements * 3)):
        if len(environment.placements) >= target_placements or environment.done:
            break
        trainer.step(trainer.generation_id, trainer.episode)
    if not environment.dictionary:
        raise RuntimeError(f"rollout {seed} did not synthesize a module")

    probes: list[tuple[int, int, dict[str, Any], dict[str, Any]]] = []
    for module in environment.dictionary[:4]:
        for rotation in module.get("rotations", [])[:8]:
            exact_anchors = exact_indexed_anchors(environment, rotation)
            anchor_count = len(anchor_signatures(exact_anchors))
            legal_count = len(
                legal_action_signatures(environment, module, rotation, exact_anchors)
            )
            probes.append((legal_count, anchor_count, module, rotation))
    if not probes:
        raise RuntimeError(f"rollout {seed} has no probe rotations")
    _, _, module, rotation = max(probes, key=lambda item: (item[0], item[1]))
    return environment, module, rotation


def run_benchmark(repetitions: int, include_rollouts: bool = True) -> dict[str, Any]:
    module, rotation = square_probe()
    scenarios: list[tuple[str, server.FloorEnvironment, dict, dict, float]] = []
    for name, columns, rows in (
        ("compact_grid_6", 3, 2),
        ("compact_grid_48", 8, 6),
        ("compact_grid_96", 12, 8),
    ):
        environment, build_ms = make_grid_environment(columns, rows)
        scenarios.append((name, environment, module, rotation, build_ms))

    if include_rollouts:
        for seed in (812, 1881):
            environment, rollout_module, rollout_rotation = rollout_environment(seed)
            scenarios.append(
                (
                    f"policy_rollout_seed_{seed}",
                    environment,
                    rollout_module,
                    rollout_rotation,
                    0.0,
                )
            )

    results = [
        evaluate_scenario(name, environment, probe_module, probe_rotation, repetitions, build_ms)
        for name, environment, probe_module, probe_rotation, build_ms in scenarios
    ]
    return {
        "benchmark": "v0.8.0 graph-frontier evaluation",
        "python": sys.version.split()[0],
        "attachment_match_limit": server.ATTACHMENT_MATCH_LIMIT,
        "attachment_frontier_limit": server.ATTACHMENT_FRONTIER_LIMIT,
        "repetitions": repetitions,
        "scenarios": results,
        "conclusion": (
            "Do not integrate the recovered raw FrontierGraph. Keep the existing "
            "incremental residual-edge graph and vector predicates. Its unbounded "
            "angle index is lossless, but the production cap is intentionally lossy."
        ),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=250)
    parser.add_argument(
        "--skip-rollouts",
        action="store_true",
        help="run only deterministic compact-grid scenarios",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.repetitions < 3:
        raise SystemExit("--repetitions must be at least 3")
    print(
        json.dumps(
            run_benchmark(args.repetitions, include_rollouts=not args.skip_rollouts),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
