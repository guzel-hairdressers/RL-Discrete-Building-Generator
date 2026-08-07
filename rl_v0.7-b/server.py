"""Module Lab v0.6-B PyTorch training and WebSocket server.

Each WebSocket owns a completely independent :class:`ParallelTrainer`.  Within
that trainer all floor environments share one policy and one optimizer.  Shape
dictionary selection and placement selection are both stochastic policy
actions, so terminal aggregate reward trains the complete design policy.

Vector geometry is authoritative for containment, overlap, adjacency, exposed
walls, perimeter, and terminal daylight.  Integer cells are used only as a
candidate-search acceleration structure.
"""

from __future__ import annotations

import asyncio
from collections import deque
import copy
import concurrent.futures
import heapq
import json
import math
import os
import time
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import torch
import torch.nn as nn
import torch.optim as optim
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import uvicorn

import geometry as G
import graph


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
MIN_SHARED_EDGE = 0.5
MAX_CORRIDOR_WIDTH = 1.5
DAYLIGHT_DEPTH = 6.0
PLACEMENT_FEATURE_DIM = 20
VECTOR_SIGNATURE_SAMPLES = 8
FLOOR_SCALAR_DIM = 12
FLOOR_DESCRIPTOR_DIM = FLOOR_SCALAR_DIM + (VECTOR_SIGNATURE_SAMPLES * 2 + 2) * 2
SITE_DESCRIPTOR_DIM = FLOOR_DESCRIPTOR_DIM
SITE_EMBEDDING_DIM = 32
POOLED_SITE_DIM = SITE_EMBEDDING_DIM * 2
LATENT_ACTION_DIM = 8
MODULE_CATEGORIES = ("core", "corridor", "room", "special")
SLOT_FEATURE_DIM = 2
ATRIUM_FEATURE_DIM = FLOOR_DESCRIPTOR_DIM
SPATIAL_BUCKET_SIZE = 8.0
SPATIAL_PADDING = 1.0e-6
ATTACHMENT_FRONTIER_LIMIT = 144
ATTACHMENT_MATCH_LIMIT = 12
ATTACHMENT_ANGLE_SCALE = 1_000_000.0
RELATIVE_TIME_WINDOW = 20
BASELINE_TRANSITION_EPISODES = 5
MAX_FRONTIER_REWARD = 4.0
UNMERGED_TRIANGLE_PENALTY = 8.0
BPE_REUSE_BONUS_PER_MODULE = 3.0


DEFAULT_SETTINGS: dict[str, Any] = {
    "boundaryType": "lobed",
    "atriumPolicy": "agent",
    "singleFloor": False,
    "publicMode": False,
    "parallelEnvironments": 4,
    "maxModules": 130,
    "learningRate": 0.05,
    "minEdge": 3.0,
    "maxEdge": 9.0,
    "maxEdges": 8,
    "dictCap": 10,
    "angleStep": 15.0,
    "coreSpacing": 8.0,
    "travelLimit": 12,
    "seed": 123,
    "allowCorridors": False,
}

BOUNDARY_TYPES = {"lobed", "lshape", "ushape", "tshape", "convex", "rect", "free"}
ATRIUM_POLICIES = {"agent", "central", "none"}


class SettingsError(ValueError):
    """Raised when a settings transaction is not valid in its entirety."""


class StaleStepError(RuntimeError):
    """Raised before mutation when a step targets an obsolete generation."""


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SettingsError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise SettingsError(f"{name} must be a finite number")
    return result


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SettingsError(f"{name} must be an integer")
    return int(value)


def _in_range(value: float, minimum: float, maximum: float, name: str) -> float:
    if not minimum <= value <= maximum:
        raise SettingsError(f"{name} must be between {minimum:g} and {maximum:g}")
    return value


def _half_step(value: float, name: str) -> float:
    if abs(value * 2.0 - round(value * 2.0)) > 1.0e-8:
        raise SettingsError(f"{name} must use 0.5 increments")
    return value


def _average_unmerged_triangle_penalty(
    triangle_count: int, floor_count: int
) -> float:
    """Apply the canonical -8 points per average unmerged triangle."""

    return UNMERGED_TRIANGLE_PENALTY * max(0, int(triangle_count)) / max(1, int(floor_count))


def _reused_bpe_module_summary(
    layout_graphs: Sequence[graph.LayoutGraph],
    episode: int = 0,
) -> tuple[int, float]:
    """Return globally reused merged occurrences and their exact bonus."""

    frequencies: dict[str, int] = {}
    for layout_graph in layout_graphs:
        for node in layout_graph.nodes.values():
            shape_type = str(node.get("shapeType", ""))
            if shape_type.startswith("M_round"):
                frequencies[shape_type] = frequencies.get(shape_type, 0) + 1
    reused_modules = sum(
        frequency for frequency in frequencies.values() if frequency >= 2
    )
    decay_factor = max(0.15, math.exp(-float(episode) / 100.0))
    bonus_per_module = BPE_REUSE_BONUS_PER_MODULE * decay_factor
    return reused_modules, min(50.0, float(bonus_per_module * reused_modules))


def validate_settings_patch(current: dict[str, Any], patch: Any) -> dict[str, Any]:
    """Validate a complete settings transaction without mutating *current*."""

    if not isinstance(patch, dict):
        raise SettingsError("settings must be an object")
    unknown = sorted(set(patch) - set(DEFAULT_SETTINGS))
    if unknown:
        raise SettingsError(f"unknown setting: {unknown[0]}")

    merged = dict(current)
    merged.update(patch)

    boundary_type = merged["boundaryType"]
    if not isinstance(boundary_type, str) or boundary_type not in BOUNDARY_TYPES:
        raise SettingsError("boundaryType is not supported")
    atrium_policy = merged["atriumPolicy"]
    if not isinstance(atrium_policy, str) or atrium_policy not in ATRIUM_POLICIES:
        raise SettingsError("atriumPolicy is not supported")
    for key in ("singleFloor", "publicMode", "allowCorridors"):
        if type(merged[key]) is not bool:
            raise SettingsError(f"{key} must be a boolean")

    merged["parallelEnvironments"] = int(
        _in_range(_integer(merged["parallelEnvironments"], "parallelEnvironments"), 1, 16, "parallelEnvironments")
    )
    merged["maxModules"] = int(
        _in_range(_integer(merged["maxModules"], "maxModules"), 10, 300, "maxModules")
    )
    merged["maxEdges"] = int(
        _in_range(_integer(merged["maxEdges"], "maxEdges"), 3, 8, "maxEdges")
    )
    merged["dictCap"] = int(
        _in_range(_integer(merged["dictCap"], "dictCap"), 3, 20, "dictCap")
    )
    merged["travelLimit"] = int(
        _in_range(_integer(merged["travelLimit"], "travelLimit"), 5, 60, "travelLimit")
    )
    merged["seed"] = int(_in_range(_integer(merged["seed"], "seed"), 0, 2**31 - 1, "seed"))

    for key in ("minEdge", "maxEdge"):
        merged[key] = _half_step(
            _in_range(_finite_number(merged[key], key), 1.0, 9.0, key),
            key,
        )
    merged["angleStep"] = _half_step(
        _in_range(_finite_number(merged["angleStep"], "angleStep"), 0.0, 90.0, "angleStep"),
        "angleStep",
    )
    if merged["minEdge"] > merged["maxEdge"]:
        raise SettingsError("minEdge cannot exceed maxEdge")
    merged["coreSpacing"] = _in_range(
        _finite_number(merged["coreSpacing"], "coreSpacing"), 0.0, 30.0, "coreSpacing"
    )
    merged["learningRate"] = _in_range(
        _finite_number(merged["learningRate"], "learningRate"), 0.01, 0.30, "learningRate"
    )
    if merged.get("allowCorridors", False):
        corridor_edge_limit = MAX_CORRIDOR_WIDTH / math.sin(math.radians(40.0))
        if merged["minEdge"] > corridor_edge_limit + 1.0e-8:
            raise SettingsError(
                "minEdge is incompatible with a 1.5m corridor and the 40° minimum-angle rule"
            )
    if not merged.get("singleFloor", False):
        basic_edge_count = min(int(merged["maxEdges"]), 4)
        maximum_core_area = (
            basic_edge_count
            * merged["maxEdge"] ** 2
            / (4.0 * math.tan(math.pi / basic_edge_count))
        )
        if maximum_core_area + 1.0e-8 < 20.0:
            raise SettingsError("maxEdge/maxEdges cannot form the required 20m² minimum core")
    return merged


def select_device() -> torch.device:
    """Choose CUDA, with a CPU fallback for fast scalar RL operations."""

    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


class PolicyModel(nn.Module):
    """Shared placement, vector-geometry, category, and atrium policy."""

    def __init__(self) -> None:
        super().__init__()
        self.placement_head = nn.Sequential(
            nn.Linear(PLACEMENT_FEATURE_DIM, 96),
            nn.LayerNorm(96),
            nn.SiLU(),
            nn.Linear(96, 48),
            nn.SiLU(),
            nn.Linear(48, 1),
        )
        self.site_encoder = nn.Sequential(
            nn.Linear(FLOOR_DESCRIPTOR_DIM, 64),
            nn.SiLU(),
            nn.Linear(64, SITE_EMBEDDING_DIM),
            nn.SiLU(),
        )
        self.category_head = nn.Sequential(
            nn.Linear(POOLED_SITE_DIM, 48),
            nn.SiLU(),
            nn.Linear(48, len(MODULE_CATEGORIES)),
        )
        self.atrium_head = nn.Sequential(
            nn.Linear(ATRIUM_FEATURE_DIM, 64),
            nn.SiLU(),
            nn.Linear(64, 32),
            nn.SiLU(),
            nn.Linear(32, 1),
        )
        self.shape_head = nn.Sequential(
            nn.Linear(POOLED_SITE_DIM, 64),
            nn.SiLU(),
        )
        self.width_head = nn.Linear(64, len(G.EDGE_PALETTE))
        self.height_head = nn.Linear(64, len(G.EDGE_PALETTE))
        self.angle_head = nn.Linear(64, len(G.ANGLE_PALETTE))
        self.shape_type_head = nn.Linear(64, len(G.PARAMETRIC_SHAPE_TYPES))

    def placement_logits(self, features: torch.Tensor) -> torch.Tensor:
        """Score every active environment's candidates in one tensor call."""

        return self.placement_head(features).squeeze(-1)

    def encode_sites(self, floor_descriptors: torch.Tensor) -> torch.Tensor:
        """Encode floors independently, then preserve mean and extreme geometry."""

        if floor_descriptors.ndim == 1:
            floor_descriptors = floor_descriptors.reshape(1, -1)
        encoded = self.site_encoder(floor_descriptors)
        return torch.cat((encoded.mean(dim=0), encoded.max(dim=0).values), dim=-1)

    def category_logits(self, pooled_site: torch.Tensor) -> torch.Tensor:
        """Score the category action for non-mandatory dictionary slots."""

        return self.category_head(pooled_site.reshape(1, -1)).squeeze(0)

    def atrium_logits(self, candidate_features: torch.Tensor) -> torch.Tensor:
        """Score valid atrium candidates, including the no-atrium action."""

        return self.atrium_head(candidate_features).squeeze(-1)

    def shape_logits(self, pooled_site: torch.Tensor) -> torch.Tensor:
        """Return flattened parameter logits for compatibility/introspection."""

        return torch.cat(self.shape_parameter_logits(pooled_site), dim=0)

    def shape_parameter_logits(self, pooled_site: torch.Tensor) -> tuple[torch.Tensor, ...]:
        """Score width, height, angle, and geometry-type palette indices."""

        features = self.shape_head(pooled_site.reshape(1, -1)).squeeze(0)
        return (
            self.width_head(features),
            self.height_head(features),
            self.angle_head(features),
            self.shape_type_head(features),
        )


@dataclass(slots=True)
class PlacementCandidate:
    """One legal vector placement and its learned feature representation."""

    module: dict
    rotation: dict
    poly: list[dict]
    cells: list[dict]
    neighbors: list[str]
    shared_overlap: float
    outer_exposure: float
    features: list[float]


def _mean(values: Sequence[float]) -> float:
    return math.fsum(values) / len(values) if values else 0.0


def _std(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    average = _mean(values)
    return math.sqrt(math.fsum((value - average) ** 2 for value in values) / len(values))


def _safe_ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator > 1.0e-9 else 0.0


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _cell_key(cell: dict) -> str:
    return G.key(cell["x"], cell["y"])


def _max_shared_overlap(first_poly: Sequence[dict], second_poly: Sequence[dict]) -> float:
    """Return the longest single coincident interval, never a disjoint sum."""

    return float(G.max_shared_overlap(first_poly, second_poly))


def _placement_category(placement: dict) -> str:
    return str(placement["category"])


def _public_module(module: dict) -> dict:
    """Return JSON-safe shared dictionary metadata without rotation caches."""

    return {
        "id": module["id"],
        "name": module.get("name", module["id"]),
        "category": module["category"],
        "family": module.get("family", "procedural"),
        "poly": module["poly"],
        "area": float(module["area"]),
        "triangle": bool(module.get("triangle", module.get("isTriangle", False))),
        "regularity": float(module.get("regularity", 0.5)),
        "minWidth": float(module.get("minWidth", G.min_polygon_width(module["poly"]))),
        "parameters": module.get("parameters", {}),
    }


def _public_merged_module(module: graph.MergedModule) -> dict:
    """Return JSON-safe shared dictionary metadata for BPE merged shapes."""
    return {
        "id": module.type_id,
        "name": module.name,
        "category": "room",  # Merged modules are typically treated as rooms
        "family": "bpe_merged",
        "poly": module.poly,
        "area": float(G.polygon_area(module.poly)),
        "triangle": False,
        "regularity": 0.5,
        "minWidth": float(G.min_polygon_width(module.poly)),
        "parameters": {},
    }



class FloorEnvironment:
    """One local floor/site sharing its dictionary and policy with its peers."""

    def __init__(
        self,
        index: int,
        boundary: dict,
        atrium_choice: dict,
        site: dict,
        offset: tuple[float, float],
        rng: G.RNG,
    ) -> None:
        self.index = index
        self.boundary = boundary
        self.atrium_choice = atrium_choice
        self.site = site
        self.offset = offset
        self.rng = rng
        self.dictionary: list[dict] = []
        self.placements: list[dict] = []
        self.placement_by_id: dict[str, dict] = {}
        self.adjacency_map: dict[str, set[str]] = {}
        self.occupied: dict[str, str] = {}
        self.module_uses: dict[str, int] = {}
        self.spatial_buckets: dict[tuple[int, int], set[str]] = {}
        self.placement_bounds: dict[str, dict[str, float]] = {}
        self.core_ids: set[str] = set()
        self.attachment_edges: dict[int, dict[str, Any]] = {}
        self.attachment_by_angle: dict[int, set[int]] = {}
        self.attachment_by_placement: dict[str, set[int]] = {}
        self.attachment_order: deque[int] = deque()
        self.next_attachment_id = 0
        self.filled_area = 0.0
        self.rentable_area = 0.0
        self.repeated_uses = 0
        self.done = False
        self.last_candidate_evaluations = 0
        self.last_unique_frontier_count = 0

    def reset(self, dictionary: Sequence[dict]) -> None:
        """Reset episode state while retaining the exact same local site."""

        self.dictionary = list(dictionary)
        self.placements = []
        self.placement_by_id = {}
        self.adjacency_map = {}
        self.occupied = {}
        self.module_uses = {module["id"]: 0 for module in dictionary}
        self.spatial_buckets = {}
        self.placement_bounds = {}
        self.core_ids = set()
        self.attachment_edges = {}
        self.attachment_by_angle = {}
        self.attachment_by_placement = {}
        self.attachment_order = deque()
        self.next_attachment_id = 0
        self.filled_area = 0.0
        self.rentable_area = 0.0
        self.repeated_uses = 0
        self.done = False
        self.last_candidate_evaluations = 0
        self.last_unique_frontier_count = 0

    @staticmethod
    def _bucket_keys(bounds: dict[str, float], padding: float = SPATIAL_PADDING) -> Iterable[tuple[int, int]]:
        """Yield every spatial bucket touched by a padded axis-aligned bbox."""

        minimum_x = math.floor((bounds["minX"] - padding) / SPATIAL_BUCKET_SIZE)
        maximum_x = math.floor((bounds["maxX"] + padding) / SPATIAL_BUCKET_SIZE)
        minimum_y = math.floor((bounds["minY"] - padding) / SPATIAL_BUCKET_SIZE)
        maximum_y = math.floor((bounds["maxY"] + padding) / SPATIAL_BUCKET_SIZE)
        for bucket_x in range(minimum_x, maximum_x + 1):
            for bucket_y in range(minimum_y, maximum_y + 1):
                yield (bucket_x, bucket_y)

    def _index_placement(self, placement: dict) -> None:
        """Insert a committed placement into the exact-query broad phase."""

        bounds = G.bounds_of(placement["poly"])
        identifier = placement["id"]
        self.placement_bounds[identifier] = bounds
        for bucket in self._bucket_keys(bounds):
            self.spatial_buckets.setdefault(bucket, set()).add(identifier)

    def _nearby_placement_ids(
        self,
        bounds: dict[str, float],
        padding: float = SPATIAL_PADDING,
    ) -> set[str]:
        """Return bbox-near IDs; callers still apply exact vector predicates."""

        nearby: set[str] = set()
        for bucket in self._bucket_keys(bounds, padding):
            nearby.update(self.spatial_buckets.get(bucket, ()))
        return nearby

    @staticmethod
    def _bounds_intersect(first: dict[str, float], second: dict[str, float]) -> bool:
        """Cheap inclusive bbox test suitable for overlap and wall contact."""

        return not (
            first["maxX"] < second["minX"] - SPATIAL_PADDING
            or first["minX"] > second["maxX"] + SPATIAL_PADDING
            or first["maxY"] < second["minY"] - SPATIAL_PADDING
            or first["minY"] > second["maxY"] + SPATIAL_PADDING
        )

    @staticmethod
    def _attachment_angle_key(first: dict, second: dict) -> int:
        angle = math.atan2(second["y"] - first["y"], second["x"] - first["x"]) % math.pi
        if math.isclose(angle, math.pi, abs_tol=1.0e-9):
            angle = 0.0
        period = int(round(math.pi * ATTACHMENT_ANGLE_SCALE))
        return int(round(angle * ATTACHMENT_ANGLE_SCALE)) % period

    @staticmethod
    def _attachment_indices(module: dict, poly: Sequence[dict]) -> list[int]:
        """Return all polygon edges for attachment, enabling multi-directional stacking."""

        return list(range(len(poly)))

    def _remove_attachment(self, edge_id: int) -> None:
        edge = self.attachment_edges.pop(edge_id, None)
        if edge is None:
            return
        angle_ids = self.attachment_by_angle.get(edge["angleKey"])
        if angle_ids is not None:
            angle_ids.discard(edge_id)
            if not angle_ids:
                self.attachment_by_angle.pop(edge["angleKey"], None)
        placement_ids = self.attachment_by_placement.get(edge["placementId"])
        if placement_ids is not None:
            placement_ids.discard(edge_id)
            if not placement_ids:
                self.attachment_by_placement.pop(edge["placementId"], None)

    def _add_attachment(
        self,
        placement: dict,
        edge_index: int,
        preferred: bool,
        first: dict | None = None,
        second: dict | None = None,
    ) -> None:
        poly = placement["poly"]
        first = first or poly[edge_index]
        second = second or poly[(edge_index + 1) % len(poly)]
        length = math.hypot(second["x"] - first["x"], second["y"] - first["y"])
        if length + 1.0e-8 < MIN_SHARED_EDGE:
            return
        edge_id = self.next_attachment_id
        self.next_attachment_id += 1
        angle_key = self._attachment_angle_key(first, second)
        edge = {
            "id": edge_id,
            "placementId": placement["id"],
            "edgeIndex": edge_index,
            "a": first,
            "b": second,
            "length": length,
            "angleKey": angle_key,
            "preferred": preferred,
        }
        self.attachment_edges[edge_id] = edge
        self.attachment_by_angle.setdefault(angle_key, set()).add(edge_id)
        self.attachment_by_placement.setdefault(placement["id"], set()).add(edge_id)
        self.attachment_order.append(edge_id)

    @staticmethod
    def _covered_attachment_intervals(
        first: dict,
        second: dict,
        polygons: Sequence[Sequence[dict]],
    ) -> list[tuple[float, float]]:
        """Return the merged exact collinear coverage intervals on first--second."""

        direction_x = float(second["x"] - first["x"])
        direction_y = float(second["y"] - first["y"])
        length_squared = direction_x * direction_x + direction_y * direction_y
        if length_squared <= G.EPSILON:
            return []
        length = math.sqrt(length_squared)
        parameter_epsilon = G.COLLINEAR_EPSILON / max(length, G.EPSILON)
        intervals: list[tuple[float, float]] = []
        for poly in polygons:
            for index, third in enumerate(poly):
                fourth = poly[(index + 1) % len(poly)]
                if not G._segments_collinear(first, second, third, fourth):
                    continue
                third_parameter = (
                    (float(third["x"]) - float(first["x"])) * direction_x
                    + (float(third["y"]) - float(first["y"])) * direction_y
                ) / length_squared
                fourth_parameter = (
                    (float(fourth["x"]) - float(first["x"])) * direction_x
                    + (float(fourth["y"]) - float(first["y"])) * direction_y
                ) / length_squared
                start = max(0.0, min(third_parameter, fourth_parameter))
                end = min(1.0, max(third_parameter, fourth_parameter))
                if end - start > parameter_epsilon:
                    intervals.append((start, end))
        if not intervals:
            return []
        intervals.sort()
        merged = [intervals[0]]
        for start, end in intervals[1:]:
            prior_start, prior_end = merged[-1]
            if start <= prior_end + parameter_epsilon:
                merged[-1] = (prior_start, max(prior_end, end))
            else:
                merged.append((start, end))
        return merged

    @classmethod
    def _attachment_residuals(
        cls,
        first: dict,
        second: dict,
        polygons: Sequence[Sequence[dict]],
    ) -> list[tuple[dict[str, float], dict[str, float]]]:
        """Subtract collinear wall coverage and retain usable exposed segments."""

        intervals = cls._covered_attachment_intervals(first, second, polygons)
        if not intervals:
            return [(first, second)]
        direction_x = float(second["x"] - first["x"])
        direction_y = float(second["y"] - first["y"])
        length = math.hypot(direction_x, direction_y)
        residual_parameters: list[tuple[float, float]] = []
        cursor = 0.0
        for start, end in intervals:
            if (start - cursor) * length + 1.0e-8 >= MIN_SHARED_EDGE:
                residual_parameters.append((cursor, start))
            cursor = max(cursor, end)
        if (1.0 - cursor) * length + 1.0e-8 >= MIN_SHARED_EDGE:
            residual_parameters.append((cursor, 1.0))
        return [
            (
                {
                    "x": float(first["x"] + direction_x * start),
                    "y": float(first["y"] + direction_y * start),
                },
                {
                    "x": float(first["x"] + direction_x * end),
                    "y": float(first["y"] + direction_y * end),
                },
            )
            for start, end in residual_parameters
        ]

    def _update_attachment_frontier(self, placement: dict, module: dict, neighbors: Sequence[str]) -> None:
        """Retire consumed walls, add recent exposed walls, and cap memory/work."""

        placement_bounds = G.bounds_of(placement["poly"])
        nearby_ids = self._nearby_placement_ids(placement_bounds)
        nearby_ids.discard(placement["id"])
        nearby_ids = {
            identifier
            for identifier in nearby_ids
            if self._bounds_intersect(placement_bounds, self.placement_bounds[identifier])
        }
        for neighbor in nearby_ids:
            for edge_id in tuple(self.attachment_by_placement.get(neighbor, ())):
                edge = self.attachment_edges.get(edge_id)
                if edge is None:
                    continue
                residuals = self._attachment_residuals(
                    edge["a"], edge["b"], [placement["poly"]]
                )
                if len(residuals) == 1 and residuals[0] == (edge["a"], edge["b"]):
                    continue
                self._remove_attachment(edge_id)
                neighbor_placement = self.placement_by_id[edge["placementId"]]
                for residual_first, residual_second in residuals:
                    self._add_attachment(
                        neighbor_placement,
                        edge["edgeIndex"],
                        edge["preferred"],
                        residual_first,
                        residual_second,
                    )

        preferred_metadata = module.get("connectionEdge") or module.get("parameters", {}).get("connectionEdge", {})
        preferred_indices = {
            value
            for value in (
                preferred_metadata.get("index") if isinstance(preferred_metadata, dict) else None,
                preferred_metadata.get("oppositeIndex") if isinstance(preferred_metadata, dict) else None,
            )
            if isinstance(value, int)
        }
        indices = self._attachment_indices(module, placement["poly"])
        # General edges enter first so canonical connection walls survive eviction longest.
        indices.sort(key=lambda index: index in preferred_indices)
        for edge_index in indices:
            first = placement["poly"][edge_index]
            second = placement["poly"][(edge_index + 1) % len(placement["poly"])]
            residuals = self._attachment_residuals(
                first,
                second,
                [self.placement_by_id[neighbor]["poly"] for neighbor in nearby_ids],
            )
            for residual_first, residual_second in residuals:
                self._add_attachment(
                    placement,
                    edge_index,
                    edge_index in preferred_indices,
                    residual_first,
                    residual_second,
                )

        while len(self.attachment_edges) > ATTACHMENT_FRONTIER_LIMIT and self.attachment_order:
            self._remove_attachment(self.attachment_order.popleft())

    def world_boundary(self) -> dict:
        dx, dy = self.offset
        return {
            "instanceIdx": self.index,
            "outer": G.translate_polygon(self.site["outer"], dx, dy),
            "holes": [G.translate_polygon(hole, dx, dy) for hole in self.site["holes"]],
            "exactArea": float(self.site["exactArea"]),
            "siteArea": float(self.site["exactArea"]),
            "family": self.boundary.get("family", self.boundary.get("type", "procedural")),
        }

    def _frontier_cells(self) -> list[dict]:
        if not self.occupied:
            distance = self.site.get("distance", {})
            cells = sorted(self.site["cells"], key=lambda cell: -float(distance.get(_cell_key(cell), 0)))
            return cells[:64]
        seen: set[str] = set()
        frontier: list[dict] = []
        cell_set = self.site["cellSet"]
        for occupied_key in self.occupied:
            x_text, y_text = occupied_key.split(",")
            x, y = int(x_text), int(y_text)
            for step_x, step_y in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                candidate = {"x": x + step_x, "y": y + step_y}
                candidate_key = _cell_key(candidate)
                if candidate_key in seen or candidate_key in self.occupied or candidate_key not in cell_set:
                    continue
                seen.add(candidate_key)
                frontier.append(candidate)
        return self.rng.shuffle(frontier)[:44]

    def adjacency(self, extra: PlacementCandidate | None = None) -> dict[str, set[str]]:
        """Build the strict >=0.5 m vector contact graph."""

        adjacency = {identifier: set(neighbors) for identifier, neighbors in self.adjacency_map.items()}
        if extra is not None:
            identifier = f"f{self.index}:candidate"
            adjacency[identifier] = set(extra.neighbors)
            for neighbor in extra.neighbors:
                adjacency.setdefault(neighbor, set()).add(identifier)
        return adjacency

    def _minimum_room_crossings(self, adjacency: dict[str, set[str]], start_id: str) -> int | None:
        """Use Dijkstra/0-1 costs to count intermediate standard rooms."""

        records = self.placement_by_id
        if start_id not in records:
            return None
        queue: list[tuple[int, str]] = [(0, start_id)]
        best: dict[str, int] = {start_id: 0}
        while queue:
            crossings, identifier = heapq.heappop(queue)
            if crossings != best.get(identifier):
                continue
            current = records[identifier]
            if current["category"] == "core":
                return crossings
            for neighbor in adjacency.get(identifier, ()):
                record = records.get(neighbor)
                if record is None:
                    continue
                increment = 1 if record["category"] == "room" else 0
                new_cost = crossings + increment
                if new_cost < best.get(neighbor, 10**9):
                    best[neighbor] = new_cost
                    heapq.heappush(queue, (new_cost, neighbor))
        return None

    def _path_distance_to_core(self, cores: Sequence[dict]) -> dict[str, float]:
        goals = {p["id"] for p in cores}
        best: dict[str, float] = {identifier: 0.0 for identifier in goals}
        queue: list[tuple[float, str]] = [(0.0, identifier) for identifier in goals]
        heapq.heapify(queue)
        while queue:
            dist, identifier = heapq.heappop(queue)
            if dist != best.get(identifier):
                continue
            for neighbor in self.adjacency_map.get(identifier, ()):
                record = self.placement_by_id[neighbor]
                d_step = math.hypot(
                    self.placement_by_id[identifier]["center"]["x"] - record["center"]["x"],
                    self.placement_by_id[identifier]["center"]["y"] - record["center"]["y"]
                )
                new_dist = dist + d_step
                if new_dist < best.get(neighbor, float('inf')):
                    best[neighbor] = new_dist
                    heapq.heappush(queue, (new_dist, neighbor))
        return best

    def _room_crossing_costs_to_core(self, core_ids: Iterable[str] | None = None) -> dict[str, int]:
        """Compute every placed node's minimum standard-room cost once."""

        goals = set(self.core_ids if core_ids is None else core_ids)
        best: dict[str, int] = {identifier: 0 for identifier in goals}
        queue: list[tuple[int, str]] = [(0, identifier) for identifier in goals]
        heapq.heapify(queue)
        while queue:
            crossings, identifier = heapq.heappop(queue)
            if crossings != best.get(identifier):
                continue
            increment = 1 if self.placement_by_id[identifier]["category"] == "room" else 0
            for neighbor in self.adjacency_map.get(identifier, ()):
                new_cost = crossings + increment
                if new_cost < best.get(neighbor, 10**9):
                    best[neighbor] = new_cost
                    heapq.heappush(queue, (new_cost, neighbor))
        return best

    def _new_room_reaches_core(
        self,
        neighbors: Sequence[str],
        room_core_costs: dict[str, int] | None = None,
    ) -> bool:
        """Check a new standard room without rebuilding a graph per candidate."""

        if not neighbors:
            return False
        if room_core_costs is not None:
            return any(
                neighbor in room_core_costs
                and room_core_costs[neighbor]
                + (1 if self.placement_by_id[neighbor]["category"] == "room" else 0)
                <= 2
                for neighbor in neighbors
            )
        adjacency = {identifier: set(items) for identifier, items in self.adjacency_map.items()}
        candidate_id = f"f{self.index}:candidate"
        records = dict(self.placement_by_id)
        records[candidate_id] = {"id": candidate_id, "category": "room"}
        adjacency[candidate_id] = set(neighbors)
        for neighbor in neighbors:
            adjacency.setdefault(neighbor, set()).add(candidate_id)

        queue: list[tuple[int, str]] = [(0, candidate_id)]
        best: dict[str, int] = {candidate_id: 0}
        while queue:
            crossings, identifier = heapq.heappop(queue)
            if crossings != best.get(identifier):
                continue
            record = records[identifier]
            if record["category"] == "core":
                return crossings <= 2
            if crossings > 2:
                continue
            for neighbor in adjacency.get(identifier, ()):
                neighbor_record = records.get(neighbor)
                if neighbor_record is None:
                    continue
                increment = 1 if neighbor_record["category"] == "room" else 0
                new_cost = crossings + increment
                if new_cost < best.get(neighbor, 10**9):
                    best[neighbor] = new_cost
                    heapq.heappush(queue, (new_cost, neighbor))
        return False

    def _candidate_features(
        self,
        module: dict,
        rotation: dict,
        poly: list[dict],
        cells: list[dict],
        neighbors: Sequence[str],
        shared_overlap: float,
        outer_exposure: float,
        settings: dict[str, Any],
        orientation_basis: float,
    ) -> list[float]:
        """Build inexpensive online features; exact envelope work is terminal."""

        area = float(module["area"])
        perimeter = max(1.0e-8, G.polygon_perimeter(poly))
        fill_area = self.filled_area
        uses = self.module_uses.get(module["id"], 0)
        daylight_proxy = 0.0
        if module["category"] in ("room", "special") and cells:
            wall_distance = self.site.get("vectorWallDistance", {})
            daylight_proxy = _mean(
                [1.0 if wall_distance.get(_cell_key(cell), math.inf) <= DAYLIGHT_DEPTH else 0.0 for cell in cells]
            )

        angle = float(rotation.get("angle", 0.0)) % 180.0
        basis = orientation_basis % 180.0
        angle_delta = abs(angle - basis)
        orientation = 1.0 - min(angle_delta, 180.0 - angle_delta) / 90.0
        center = G.polygon_centroid(poly)
        cores = [self.placement_by_id[identifier] for identifier in self.core_ids]
        if cores:
            core_distance = min(
                math.hypot(center["x"] - item["center"]["x"], center["y"] - item["center"]["y"])
                for item in cores
            )
            travel_score = 1.0 - _clamp(core_distance / max(1.0, float(settings["travelLimit"])))
            core_proximity = 1.0 - _clamp(core_distance / 30.0)
        else:
            travel_score = 0.0
            core_proximity = 0.0

        category = module["category"]
        outer_ratio = _clamp(outer_exposure / perimeter)
        corridor_interior = 1.0 - outer_ratio if category == "corridor" else 0.0
        triangle = bool(module.get("triangle", module.get("isTriangle", False)))
        true_width = float(module.get("minWidth", G.min_polygon_width(poly)))
        return [
            _clamp(area / max(1.0, float(self.site["exactArea"]))),
            _clamp(shared_overlap / perimeter),
            _clamp(uses / 5.0) if uses else -0.25,
            daylight_proxy,
            _clamp(shared_overlap / max(1.0, perimeter - shared_overlap)),
            float(module.get("regularity", 0.5)),
            orientation,
            corridor_interior,
            -1.0 if triangle else 0.0,
            core_proximity,
            -2.0 * outer_ratio if category == "corridor" else -0.25 * outer_ratio,
            1.0 if category == "core" else 0.0,
            1.0 if category == "corridor" else 0.0,
            1.0 if category == "room" else 0.0,
            1.0 if category == "special" else 0.0,
            _clamp(true_width / 10.0),
            _clamp(len(poly) / 12.0),
            _clamp(fill_area / max(1.0, float(self.site["exactArea"]))),
            travel_score,
            1.0 if module.get("edgeRangeCompatible", True) else -1.0,
        ]

    def _candidate_from_anchor(
        self,
        module: dict,
        rotation: dict,
        anchor_x: float,
        anchor_y: float,
        settings: dict[str, Any],
        orientation_basis: float,
        room_core_costs: dict[str, int],
        cg_sub_totals: dict[str, float] | None = None,
    ) -> PlacementCandidate | None:
        rot_poly = rotation["poly"]
        rot_bounds = rotation.get("bounds")
        if rot_bounds is None:
            rot_bounds = G.bounds_of(rot_poly)
            rotation["bounds"] = rot_bounds

        min_x = rot_bounds["minX"] + anchor_x
        max_x = rot_bounds["maxX"] + anchor_x
        min_y = rot_bounds["minY"] + anchor_y
        max_y = rot_bounds["maxY"] + anchor_y

        site_bounds = self.site["bounds"]
        if (
            min_x < site_bounds["minX"] - 1.0e-7
            or max_x > site_bounds["maxX"] + 1.0e-7
            or min_y < site_bounds["minY"] - 1.0e-7
            or max_y > site_bounds["maxY"] + 1.0e-7
        ):
            return None

        poly = G.translate_polygon(rot_poly, anchor_x, anchor_y)
        bounds = {"minX": min_x, "maxX": max_x, "minY": min_y, "maxY": max_y}

        t_overlap = time.perf_counter()
        if not self.placements:
            nearby = []
            has_overlap = False
        else:
            nearby_ids = {
                identifier
                for identifier in self._nearby_placement_ids(bounds)
                if self._bounds_intersect(bounds, self.placement_bounds[identifier])
            }
            nearby = [self.placement_by_id[identifier] for identifier in nearby_ids]
            has_overlap = any(G.polygons_overlap(poly, placement["poly"]) for placement in nearby)
        if cg_sub_totals is not None:
            cg_sub_totals["cgOverlapCollisions"] += time.perf_counter() - t_overlap
        if has_overlap:
            return None

        t_boundary = time.perf_counter()
        inside = G.polygon_inside_site(poly, self.site["outer"], self.site["holes"])
        if cg_sub_totals is not None:
            cg_sub_totals["cgSiteBoundary"] += time.perf_counter() - t_boundary
        if not inside:
            return None

        cells: list[dict] = []

        category = module["category"]
        if category == "corridor" and G.min_polygon_width(poly) > MAX_CORRIDOR_WIDTH + 1.0e-8:
            return None

        center = G.polygon_centroid(poly)
        if category == "core":
            spacing = float(settings["coreSpacing"])
            nearby_core_ids = self._nearby_placement_ids(bounds, padding=spacing + SPATIAL_PADDING)
            for identifier in nearby_core_ids:
                if identifier not in self.core_ids:
                    continue
                placement = self.placement_by_id[identifier]
                dist = math.hypot(center["x"] - placement["center"]["x"], center["y"] - placement["center"]["y"])
                if dist + 1.0e-8 < spacing:
                    separated = False
                    if self.site.get("holes"):
                        for hole in self.site["holes"]:
                            for k in range(len(hole)):
                                q1 = hole[k]
                                q2 = hole[(k + 1) % len(hole)]
                                if G._segment_intersection_kind(center, placement["center"], q1, q2) == "proper":
                                    separated = True
                                    break
                            if separated:
                                break
                    if not separated:
                        return None

        t_neigh = time.perf_counter()
        neighbors: list[str] = []
        shared_overlap = 0.0
        for placement in nearby:
            max_ovlp, total_ovlp = G.shared_overlap_pair(poly, placement["poly"])
            if max_ovlp + 1.0e-8 >= MIN_SHARED_EDGE:
                neighbors.append(placement["id"])
                shared_overlap += total_ovlp
        if self.placements and not neighbors and category != "core":
            return None
        if category == "room" and self.placements:
            if self.core_ids and not self._new_room_reaches_core(neighbors, room_core_costs):
                return None

        outer_exposure = G.get_shared_overlap(poly, self.site["outer"])
        if cg_sub_totals is not None:
            cg_sub_totals["cgNeighborAnalysis"] += time.perf_counter() - t_neigh
        t_feat = time.perf_counter()
        features = self._candidate_features(
            module,
            rotation,
            poly,
            cells,
            neighbors,
            shared_overlap,
            outer_exposure,
            settings,
            orientation_basis,
        )
        if cg_sub_totals is not None:
            cg_sub_totals["cgFeatureExtraction"] += time.perf_counter() - t_feat
        return PlacementCandidate(
            module=module,
            rotation=rotation,
            poly=poly,
            cells=cells,
            neighbors=neighbors,
            shared_overlap=shared_overlap,
            outer_exposure=outer_exposure,
            features=features,
        )

    def _edge_alignment_anchors(
        self,
        module: dict,
        rotation: dict,
        include_edge_id: bool = False,
    ) -> Iterable[tuple]:
        """Yield anchors from a bounded, angle-indexed exposed-edge frontier."""

        candidate_poly = rotation["poly"]
        angle_period = int(round(math.pi * ATTACHMENT_ANGLE_SCALE))
        for candidate_index in self._attachment_indices(module, candidate_poly):
            candidate_first = candidate_poly[candidate_index]
            candidate_second = candidate_poly[(candidate_index + 1) % len(candidate_poly)]
            candidate_dx = candidate_second["x"] - candidate_first["x"]
            candidate_dy = candidate_second["y"] - candidate_first["y"]
            candidate_length = math.hypot(candidate_dx, candidate_dy)
            if candidate_length < MIN_SHARED_EDGE:
                continue
            angle_key = self._attachment_angle_key(candidate_first, candidate_second)
            raw_edge_ids: set[int] = set()
            for delta in (-2, -1, 0, 1, 2):
                lookup = (angle_key + delta) % angle_period
                raw_edge_ids.update(self.attachment_by_angle.get(lookup, ()))
            edge_ids = {eid for eid in raw_edge_ids if eid in self.attachment_edges}
            prioritized = sorted(
                edge_ids,
                key=lambda edge_id: (
                    bool(self.attachment_edges[edge_id]["preferred"]),
                    edge_id,
                ),
                reverse=True,
            )[:ATTACHMENT_MATCH_LIMIT]
            for edge_id in prioritized:
                edge = self.attachment_edges[edge_id]
                placed_first = edge["a"]
                placed_second = edge["b"]
                placed_dx = placed_second["x"] - placed_first["x"]
                placed_dy = placed_second["y"] - placed_first["y"]
                placed_length = edge["length"]
                cross = placed_dx * candidate_dy - placed_dy * candidate_dx
                if abs(cross) > 1.0e-7 * placed_length * candidate_length:
                    continue
                dot = placed_dx * candidate_dx + placed_dy * candidate_dy
                if dot < 0.0:
                    if include_edge_id:
                        yield (
                            placed_second["x"] - candidate_first["x"],
                            placed_second["y"] - candidate_first["y"],
                            edge_id,
                        )
                        yield (
                            placed_first["x"] - candidate_second["x"],
                            placed_first["y"] - candidate_second["y"],
                            edge_id,
                        )
                    else:
                        yield (
                            placed_second["x"] - candidate_first["x"],
                            placed_second["y"] - candidate_first["y"],
                        )
                        yield (
                            placed_first["x"] - candidate_second["x"],
                            placed_first["y"] - candidate_second["y"],
                        )
                else:
                    if include_edge_id:
                        yield (
                            placed_first["x"] - candidate_first["x"],
                            placed_first["y"] - candidate_first["y"],
                            edge_id,
                        )
                        yield (
                            placed_second["x"] - candidate_second["x"],
                            placed_second["y"] - candidate_second["y"],
                            edge_id,
                        )
                    else:
                        yield (
                            placed_first["x"] - candidate_first["x"],
                            placed_first["y"] - candidate_first["y"],
                        )
                        yield (
                            placed_second["x"] - candidate_second["x"],
                            placed_second["y"] - candidate_second["y"],
                        )
                if include_edge_id:
                    yield (
                        (placed_first["x"] + placed_second["x"] - candidate_first["x"] - candidate_second["x"])
                        * 0.5,
                        (placed_first["y"] + placed_second["y"] - candidate_first["y"] - candidate_second["y"])
                        * 0.5,
                        edge_id,
                    )
                else:
                    yield (
                        (placed_first["x"] + placed_second["x"] - candidate_first["x"] - candidate_second["x"])
                        * 0.5,
                        (placed_first["y"] + placed_second["y"] - candidate_first["y"] - candidate_second["y"])
                        * 0.5,
                    )

    def _validate_edge_alignment(self, candidate_poly: Sequence[dict]) -> bool:
        """Enforce strict edge alignment rules for all shared contacts.
        
        For any shared contact between Edge A (candidate) and Edge B (other):
        1. The ratio of their lengths (LA/LB) must be exactly 1:1, 1:2, or 2:1 (within 5e-3).
        2. The shared overlap length must be exactly equal to the shorter of the two edges.
        3. If one edge is twice as long as the other, the overlap on the longer edge must be exactly 50%
           and must be flush with either the left end (start <= 0.01) or the right end (end >= 0.99) of the longer edge.
        """
        for i, first in enumerate(candidate_poly):
            second = candidate_poly[(i + 1) % len(candidate_poly)]
            dx = second["x"] - first["x"]
            dy = second["y"] - first["y"]
            len_a = math.hypot(dx, dy)
            if len_a <= 1e-4:
                continue
            
            for placement in self.placements:
                other_poly = placement["poly"]
                for j, third in enumerate(other_poly):
                    fourth = other_poly[(j + 1) % len(other_poly)]
                    len_b = math.hypot(fourth["x"] - third["x"], fourth["y"] - third["y"])
                    if len_b <= 1e-4:
                        continue
                    
                    interval = G._overlap_interval_on_first(first, second, third, fourth)
                    if interval is not None:
                        start, end = interval
                        
                        interval_other = G._overlap_interval_on_first(third, fourth, first, second)
                        if interval_other is None:
                            return False
                        
                        start_other, end_other = interval_other
                        
                        # 1. Enforce length ratio of 1:1, 1:2, or 2:1
                        ratio = len_a / len_b
                        is_1_1 = abs(ratio - 1.0) < 5e-3
                        is_2_1 = abs(ratio - 2.0) < 5e-3
                        is_1_2 = abs(ratio - 0.5) < 5e-3
                        
                        if not (is_1_1 or is_2_1 or is_1_2):
                            # The length ratio is illegal!
                            return False
                            
                        # 2. Overlap must be 100% of the shorter edge
                        # If ratio is 1:1, overlap must be 100% of both (start ~ 0.0, end ~ 1.0)
                        if is_1_1:
                            if not (start < 0.01 and end > 0.99):
                                return False
                                
                        # If ratio is 2:1 (A is twice as long as B), overlap must be 100% of B
                        # which means overlap on A must be exactly 50% (either [0.0, 0.5] or [0.5, 1.0])
                        elif is_2_1:
                            if not (start_other < 0.01 and end_other > 0.99):
                                return False
                            overlap_a = end - start
                            if not (abs(overlap_a - 0.5) < 0.01):
                                return False
                            if not (start < 0.01 or end > 0.99):
                                return False
                                
                        # If ratio is 1:2 (B is twice as long as A), overlap must be 100% of A
                        # which means overlap on B must be exactly 50% (either [0.0, 0.5] or [0.5, 1.0])
                        elif is_1_2:
                            if not (start < 0.01 and end > 0.99):
                                return False
                            overlap_b = end_other - start_other
                            if not (abs(overlap_b - 0.5) < 0.01):
                                return False
                            if not (start_other < 0.01 or end_other > 0.99):
                                return False
                                
        return True

    def generate_candidates(
        self,
        settings: dict[str, Any],
        orientation_basis: float,
        limit: int = 128,
        profiler: StepProfiler | None = None,
    ) -> list[PlacementCandidate]:
        """Generate legal actions with exact vector contacts and bounded work."""

        cg_start = time.perf_counter() if profiler is not None else 0.0
        placing_first = not self.placements
        self.last_candidate_evaluations = 0
        self.last_unique_frontier_count = 0
        single_floor = bool(settings["singleFloor"])
        modules = self.rng.shuffle(self.dictionary)
        if placing_first and not single_floor:
            modules = [module for module in modules if module["category"] == "core"]
        core_candidates: list[PlacementCandidate] = []
        room_candidates: list[PlacementCandidate] = []
        seen: set[tuple] = set()
        frontier = self._frontier_cells() if placing_first else []
        room_core_costs = self._room_crossing_costs_to_core() if self.core_ids else {}

        cat_limit = max(8, limit)
        checked_edges = set()
        successful_edges = set()
        early_break = False

        cg_sub_totals = {
            "cgAnchorSearch": 0.0,
            "cgOverlapCollisions": 0.0,
            "cgSiteBoundary": 0.0,
            "cgNeighborAnalysis": 0.0,
            "cgEdgeAlignment": 0.0,
            "cgFeatureExtraction": 0.0,
        }

        # Pass 1: Generate all rooms and aligned (connected) cores
        for module in modules:
            category = module["category"]
            rotations = self.rng.shuffle(module["rotations"])
            for rotation in rotations:
                t_anchor_start = time.perf_counter()
                if placing_first:
                    rotation_cells = rotation["cells"][:8]
                    anchors_list = [
                        (target["x"] - cell["x"], target["y"] - cell["y"], None)
                        for target in frontier
                        for cell in rotation_cells
                    ]
                else:
                    anchors_list = list(self._edge_alignment_anchors(module, rotation, include_edge_id=True))
                cg_sub_totals["cgAnchorSearch"] += time.perf_counter() - t_anchor_start
                for anchor_x, anchor_y, edge_id in anchors_list:
                    if edge_id is not None:
                        checked_edges.add(edge_id)
                    signature = (
                        module["id"],
                        round(float(rotation.get("angle", 0.0)), 6),
                        round(anchor_x, 6),
                        round(anchor_y, 6),
                    )
                    if signature in seen:
                        continue
                    seen.add(signature)
                    self.last_candidate_evaluations += 1
                    candidate = self._candidate_from_anchor(
                        module,
                        rotation,
                        anchor_x,
                        anchor_y,
                        settings,
                        orientation_basis,
                        room_core_costs,
                        cg_sub_totals=cg_sub_totals,
                    )
                    if candidate is not None:
                        if not placing_first:
                            t_align = time.perf_counter()
                            is_valid = self._validate_edge_alignment(candidate.poly)
                            cg_sub_totals["cgEdgeAlignment"] += time.perf_counter() - t_align
                            if not is_valid:
                                continue
                        
                        if category == "core":
                            core_candidates.append(candidate)
                        else:
                            room_candidates.append(candidate)
                            
                        if edge_id is not None:
                            successful_edges.add(edge_id)
                            
                        if len(core_candidates) >= cat_limit and len(room_candidates) >= cat_limit:
                            early_break = True
                            break
                if early_break:
                    break
            if early_break:
                break

        if not placing_first and not early_break:
            # Delete edges that were checked but failed to produce any valid candidates
            unattachable_edges = checked_edges - successful_edges
            for edge_id in unattachable_edges:
                self._remove_attachment(edge_id)

        # Pass 2: If we are not placing_first, and there are NO opportunities left on existing islands
        # (meaning both room_candidates and core_candidates from Pass 1 are empty),
        # only then do we try to generate remote (disconnected) core candidates on core_frontier.
        if not placing_first and not room_candidates and not core_candidates:
            core_modules = [m for m in modules if m["category"] == "core"]
            if core_modules:
                unoccupied_cells = [cell for cell in self.site["cells"] if _cell_key(cell) not in self.occupied]
                distance = self.site.get("distance", {})
                core_frontier = sorted(unoccupied_cells, key=lambda cell: -float(distance.get(_cell_key(cell), 0)))[:64]
                
                for module in core_modules:
                    rotations = self.rng.shuffle(module["rotations"])
                    for rotation in rotations:
                        rotation_cells = rotation["cells"][:8]
                        anchors = [
                            (target["x"] - cell["x"], target["y"] - cell["y"])
                            for target in core_frontier
                            for cell in rotation_cells
                        ]
                        for anchor_x, anchor_y in anchors:
                            signature = (
                                module["id"],
                                round(float(rotation.get("angle", 0.0)), 6),
                                round(anchor_x, 6),
                                round(anchor_y, 6),
                            )
                            if signature in seen:
                                continue
                            seen.add(signature)
                            self.last_candidate_evaluations += 1
                            candidate = self._candidate_from_anchor(
                                module,
                                rotation,
                                anchor_x,
                                anchor_y,
                                settings,
                                orientation_basis,
                                room_core_costs,
                                cg_sub_totals=cg_sub_totals,
                            )
                            if candidate is not None:
                                core_candidates.append(candidate)
                                if len(core_candidates) >= cat_limit:
                                    break
                        if len(core_candidates) >= cat_limit:
                            break
                    if len(core_candidates) >= cat_limit:
                        break

        self.last_unique_frontier_count = (
            len(frontier) if placing_first else len(successful_edges)
        )
        if profiler is not None:
            cg_total = time.perf_counter() - cg_start
            cg_tracked = sum(cg_sub_totals.values())
            cg_sub_totals["cgOther"] = max(0.0, cg_total - cg_tracked)
            for label, total_sec in cg_sub_totals.items():
                profiler.record(label, total_sec)
            profiler.record("candidateGeneration", cg_total)
        return core_candidates[:cat_limit] + room_candidates[:cat_limit]

    def place(self, candidate: PlacementCandidate) -> dict:
        """Commit one candidate and return its world-space protocol record."""

        identifier = f"f{self.index}:p{len(self.placements)}"
        center = G.polygon_centroid(candidate.poly)
        placed_cells = candidate.cells or G.rasterize_polygon(candidate.poly)
        placement = {
            "id": identifier,
            "moduleId": candidate.module["id"],
            "shapeType": candidate.module.get("shapeType", candidate.module.get("type", candidate.module["id"])),
            "category": candidate.module["category"],
            "family": candidate.module.get("family", "procedural"),
            "poly": candidate.poly,
            "cells": placed_cells,
            "center": center,
            "rotation": float(candidate.rotation.get("angle", 0.0)),
            "area": float(candidate.module["area"]),
            "regularity": float(candidate.module.get("regularity", 0.5)),
            "triangle": bool(candidate.module.get("triangle", candidate.module.get("isTriangle", False))),
            "outerExposure": float(candidate.outer_exposure),
            "neighbors": list(candidate.neighbors),
            "bornAt": time.time() * 1000.0,
            "instanceIdx": self.index,
        }
        self.placements.append(placement)
        self.placement_by_id[identifier] = placement
        self.adjacency_map[identifier] = set(candidate.neighbors)
        for neighbor in candidate.neighbors:
            self.adjacency_map.setdefault(neighbor, set()).add(identifier)
        for cell in placed_cells:
            self.occupied[_cell_key(cell)] = identifier
        prior_uses = self.module_uses.get(candidate.module["id"], 0)
        self.module_uses[candidate.module["id"]] = prior_uses + 1
        if prior_uses:
            self.repeated_uses += 1
        self.filled_area += placement["area"]
        if placement["category"] in ("room", "special"):
            self.rentable_area += placement["area"]
        if placement["category"] == "core":
            self.core_ids.add(identifier)
        self._index_placement(placement)
        self._update_attachment_frontier(placement, candidate.module, candidate.neighbors)

        dx, dy = self.offset
        world_center = {"x": center["x"] + dx, "y": center["y"] + dy}
        return {
            "id": identifier,
            "instanceIdx": self.index,
            "poly": G.translate_polygon(candidate.poly, dx, dy),
            "center": world_center,
            "rotation": placement["rotation"],
            "area": placement["area"],
            "neighbors": list(candidate.neighbors),
            "module": {
                "id": candidate.module["id"],
                "category": candidate.module["category"],
                "family": candidate.module.get("family", "procedural"),
                "triangle": placement["triangle"],
            },
        }

    def online_metrics(self) -> dict[str, Any]:
        filled = self.filled_area
        rentable = self.rentable_area
        return {
            "instanceIdx": self.index,
            "filledArea": filled,
            "siteArea": float(self.site["exactArea"]),
            "fillRatio": _safe_ratio(filled, float(self.site["exactArea"])),
            "rentableArea": rentable,
            "rentableRatio": _safe_ratio(rentable, filled),
            "moduleCount": len(self.placements),
            "reuseRatio": _safe_ratio(self.repeated_uses, len(self.placements)),
            "done": self.done,
        }

    def validate_topology(self, single_floor: bool, core_spacing: float) -> tuple[bool, list[str]]:
        """Validate terminal graph constraints with shortest room-cost paths."""

        violations: list[str] = []
        if not self.placements:
            return False, ["emptyLayout"]
        if not single_floor and self.placements[0]["category"] != "core":
            violations.append("firstPlacementNotCore")

        cores = [placement for placement in self.placements if placement["category"] == "core"]
        if not single_floor and not cores:
            violations.append("missingCore")
        core_ids = {c["id"] for c in cores}
        visited_cores = set()
        for core in cores:
            cid = core["id"]
            if cid in visited_cores:
                continue
            cluster_area = 0.0
            queue = [cid]
            visited_cores.add(cid)
            while queue:
                curr_id = queue.pop(0)
                curr_placement = self.placement_by_id[curr_id]
                cluster_area += float(curr_placement.get("area", G.polygon_area(curr_placement["poly"])))
                for neighbor_id in self.adjacency_map.get(curr_id, ()):
                    if neighbor_id in core_ids and neighbor_id not in visited_cores:
                        visited_cores.add(neighbor_id)
                        queue.append(neighbor_id)
            if cluster_area + 1.0e-8 < 24.0:
                violations.append("coreAreaUnder24m2")
        for first_index, first in enumerate(cores):
            for second in cores[first_index + 1 :]:
                distance = math.hypot(
                    first["center"]["x"] - second["center"]["x"],
                    first["center"]["y"] - second["center"]["y"],
                )
                if distance + 1.0e-8 < core_spacing:
                    separated = False
                    if self.site.get("holes"):
                        for hole in self.site["holes"]:
                            for k in range(len(hole)):
                                q1 = hole[k]
                                q2 = hole[(k + 1) % len(hole)]
                                if G._segment_intersection_kind(first["center"], second["center"], q1, q2) == "proper":
                                    separated = True
                                    break
                            if separated:
                                break
                    if not separated:
                        violations.append("coreSpacing")

        room_core_distances = self._path_distance_to_core(cores)
        for placement in self.placements:
            category = placement["category"]
            if category in ("room", "special") and cores:
                dist = room_core_distances.get(placement["id"], float('inf'))
                if dist > 30.0:
                    violations.append("travelLimitCap")
                elif dist == float('inf'):
                    violations.append("noPathToCore")
        return not violations, sorted(set(violations))

    def terminal_metrics(self, single_floor: bool, core_spacing: float) -> dict[str, Any]:
        """Compute exact vector walls, perimeter, and daylight once terminal."""

        online = self.online_metrics()
        polygons = [placement["poly"] for placement in self.placements]
        segments = G.exposed_wall_segments(polygons)
        exposed_perimeter = math.fsum(float(segment["length"]) for segment in segments)
        site_daylight_samples = 0
        envelope_daylight_samples = 0
        rentable_samples = 0
        for placement in self.placements:
            if placement["category"] not in ("room", "special"):
                continue
            for cell in placement["cells"]:
                point = {"x": cell["x"] + 0.5, "y": cell["y"] + 0.5}
                rentable_samples += 1
                if G.point_to_segments_dist(point, self.site["wallSegments"]) <= DAYLIGHT_DEPTH:
                    site_daylight_samples += 1
                if G.point_to_segments_dist(point, segments) <= DAYLIGHT_DEPTH:
                    envelope_daylight_samples += 1

        corridor_perimeter = math.fsum(
            G.polygon_perimeter(placement["poly"])
            for placement in self.placements
            if placement["category"] == "corridor"
        )
        outer_corridor = math.fsum(
            float(placement["outerExposure"])
            for placement in self.placements
            if placement["category"] == "corridor"
        )
        triangle_area = math.fsum(
            float(placement["area"]) for placement in self.placements if placement["triangle"]
        )
        regularity = _mean([float(placement["regularity"]) for placement in self.placements])
        topology_valid, violations = self.validate_topology(single_floor, core_spacing)
        filled = float(online["filledArea"])
        envelope_efficiency = _clamp(4.0 * math.pi * filled / max(1.0e-8, exposed_perimeter**2))
        constructibility = _clamp(regularity * (1.0 - 0.5 * _safe_ratio(triangle_area, filled)))

        internal_exposed_perimeter = 0.0
        for segment in segments:
            mid = {
                "x": 0.5 * (segment["a"]["x"] + segment["b"]["x"]),
                "y": 0.5 * (segment["a"]["y"] + segment["b"]["y"])
            }
            dist_to_outer = G.point_to_segments_dist(mid, self.site["wallSegments"])
            
            dist_to_atrium = float('inf')
            if self.atrium_choice and self.atrium_choice.get("holes"):
                for hole in self.atrium_choice["holes"]:
                    hole_segs = []
                    for k in range(len(hole)):
                        p1 = hole[k]
                        p2 = hole[(k + 1) % len(hole)]
                        hole_segs.append({
                            "a": p1,
                            "b": p2,
                            "length": math.hypot(p2["x"] - p1["x"], p2["y"] - p1["y"])
                        })
                    dist_to_atrium = min(dist_to_atrium, G.point_to_segments_dist(mid, hole_segs))
            
            if dist_to_outer > 0.05 and dist_to_atrium > 0.05:
                internal_exposed_perimeter += float(segment["length"])

        total_partial_length = 0.0
        for p_idx, placement in enumerate(self.placements):
            poly = placement["poly"]
            for i in range(len(poly)):
                first = poly[i]
                second = poly[(i + 1) % len(poly)]
                edge_len = math.hypot(second["x"] - first["x"], second["y"] - first["y"])
                if edge_len <= 1e-4:
                    continue
                
                total_overlap = 0.0
                for other_idx, other_placement in enumerate(self.placements):
                    if other_idx == p_idx:
                        continue
                    other_poly = other_placement["poly"]
                    for j in range(len(other_poly)):
                        third = other_poly[j]
                        fourth = other_poly[(j + 1) % len(other_poly)]
                        interval = G._overlap_interval_on_first(first, second, third, fourth)
                        if interval is not None:
                            start, end = interval
                            total_overlap += (end - start) * edge_len
                
                if 0.05 < total_overlap < edge_len - 0.05:
                    total_partial_length += edge_len

        return {
            **online,
            "daylightRatio": _safe_ratio(site_daylight_samples, rentable_samples),
            "siteDaylightRatio": _safe_ratio(site_daylight_samples, rentable_samples),
            "envelopeDaylightRatio": _safe_ratio(envelope_daylight_samples, rentable_samples),
            "exposedPerimeter": exposed_perimeter,
            "envelopeEfficiency": envelope_efficiency,
            "constructibilityScore": constructibility,
            "lightScore": _safe_ratio(site_daylight_samples, rentable_samples),
            "exteriorCorridorRatio": _safe_ratio(outer_corridor, corridor_perimeter),
            "triangleRatio": _safe_ratio(triangle_area, filled),
            "topologyValid": topology_valid,
            "topologyViolations": violations,
            "internalExposedPerimeter": internal_exposed_perimeter,
            "totalPartialLength": total_partial_length,
        }


class StepProfiler:
    """Lightweight per-episode timing profiler for step and evaluation phases."""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        self._samples: dict[str, list[float]] = {}
    
    def record(self, label: str, duration_seconds: float) -> None:
        self._samples.setdefault(label, []).append(duration_seconds * 1000.0)  # Store as ms
    
    def summary(self) -> dict[str, Any]:
        result = {}
        for label, values in self._samples.items():
            if values:
                result[label] = {
                    "avg": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values),
                    "count": len(values),
                }
        return result


class ParallelTrainer:
    """Session-local shared-policy trainer for a dynamic set of floor sites."""

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        self.settings = validate_settings_patch(DEFAULT_SETTINGS, settings or {})
        self.device = select_device()
        self.step_profiler = StepProfiler()
        self.model = PolicyModel().to(self.device)
        self.optimizer = optim.Adam(self.model.parameters(), lr=float(self.settings["learningRate"]))
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)
        self.generation_id = 0
        self.episode = 0
        self.step_number = 0
        self.episode_start_time: float | None = None
        self.environments: list[FloorEnvironment] = []
        self.dictionary: list[dict] = []
        self.shape_log_probs: list[torch.Tensor] = []
        self.placement_log_probs: list[torch.Tensor] = []
        self.baseline = 0.35
        self.score_history: list[float] = []
        self.best_score = 0.0
        self.topology_multiplier = 0.05
        self.last_loss = 0.0
        self.generation_time_history: deque[float] = deque(maxlen=RELATIVE_TIME_WINDOW)
        self.frontier_growth_history: deque[float] = deque(maxlen=RELATIVE_TIME_WINDOW)
        self.generation_time_baseline: float | None = None
        self.frontier_growth_baseline: float | None = None
        self.baseline_transition_remaining = 0
        self.baseline_transition_anchor_reward = 0.0
        self.reward_settings_signature = (self._reward_signature(self.settings), None, None)
        self.last_frontier_reward = 0.0
        self._reset_episode_reward_telemetry()

    @staticmethod
    def _reward_signature(settings: dict[str, Any]) -> tuple[Any, ...]:
        """Settings that materially change candidate-search cost."""

        return (
            settings["boundaryType"],
            settings["atriumPolicy"],
            bool(settings["singleFloor"]),
            int(settings["parallelEnvironments"]),
            int(settings["maxModules"]),
            float(settings["minEdge"]),
            float(settings["maxEdge"]),
            int(settings["maxEdges"]),
            int(settings["dictCap"]),
            float(settings["angleStep"]),
            float(settings["coreSpacing"]),
            int(settings["travelLimit"]),
            int(settings["seed"]),
        )

    @staticmethod
    def _reward_site_fingerprint(environments: Sequence[FloorEnvironment]) -> tuple[Any, ...]:
        """Compact deterministic description of candidate-search geometry."""

        return tuple(
            (
                round(float(environment.site["exactArea"]), 6),
                len(environment.site["outer"]),
                len(environment.site["holes"]),
                round(float(environment.site["outerPerimeter"]), 6),
                round(float(environment.site["innerPerimeter"]), 6),
            )
            for environment in environments
        )

    @staticmethod
    def _reward_dictionary_fingerprint(dictionary: Sequence[dict]) -> tuple[Any, ...]:
        return tuple(
            (
                module.get("category", "room"),
                round(float(module.get("area", G.polygon_area(module["poly"]))), 6),
                len(module["poly"]),
                len(module.get("rotations", [])),
            )
            for module in dictionary
        )

    def _reset_episode_reward_telemetry(self) -> None:
        self.episode_generation_seconds = 0.0
        self.episode_action_normalized_seconds = 0.0
        self.episode_candidate_evaluations = 0
        self.episode_frontier_growth = 0.0
        self.episode_frontier_samples = 0

    def _record_frontier_sample(
        self,
        environment: FloorEnvironment,
        elapsed_seconds: float,
    ) -> None:
        """Record hardware time and the corresponding legal open frontier."""

        elapsed = max(0.0, float(elapsed_seconds))
        evaluations = max(1, int(environment.last_candidate_evaluations))
        unique_frontiers = max(0, int(environment.last_unique_frontier_count))
        self.episode_generation_seconds += elapsed
        self.episode_candidate_evaluations += evaluations
        self.episode_action_normalized_seconds += (
            elapsed * max(1, unique_frontiers) / evaluations
        )
        placed = max(1, len(environment.placements))
        # Only distinct exposed attachment edges/cells count. Module and
        # rotation variants of one edge cannot inflate this signal.
        growth = math.log1p(unique_frontiers) / placed
        self.episode_frontier_growth += growth
        self.episode_frontier_samples += 1

    def _relative_frontier_reward(self) -> dict[str, float | int]:
        """Return a rolling-baseline reward with small-module exploit control."""

        placements = [
            placement
            for environment in self.environments
            for placement in environment.placements
        ]
        areas = [float(placement.get("area", G.polygon_area(placement["poly"]))) for placement in placements]
        mean_area = _mean(areas)
        # Eight square metres is the absolute anti-fragmentation floor; the
        # relative term also catches pieces that are tiny for the active kit.
        small_threshold = max(8.0, mean_area * 0.5)
        small_ratio = _safe_ratio(sum(area < small_threshold for area in areas), len(areas))
        area_normalizer = _clamp(mean_area / 12.0, 0.5, 2.0) if areas else 1.0
        effective_time = self.episode_action_normalized_seconds * area_normalizer / (1.0 + small_ratio)
        frontier_growth = _safe_ratio(
            self.episode_frontier_growth,
            self.episode_frontier_samples,
        ) / (1.0 + small_ratio)

        if self.generation_time_baseline is None:
            time_relative = 0.0
            frontier_relative = 0.0
            self.generation_time_baseline = max(1.0e-9, effective_time)
            self.frontier_growth_baseline = max(1.0e-9, frontier_growth)
            time_reference = self.generation_time_baseline
            frontier_reference = self.frontier_growth_baseline
        else:
            time_reference = max(1.0e-9, self.generation_time_baseline)
            frontier_reference = max(1.0e-9, self.frontier_growth_baseline or 0.0)
            time_relative = _clamp((effective_time - time_reference) / time_reference, -1.0, 1.0)
            frontier_relative = _clamp(
                (frontier_growth - frontier_reference) / frontier_reference,
                -1.0,
                1.0,
            )

        exploit_penalty = 2.0 * small_ratio
        unblended_reward = _clamp(
            MAX_FRONTIER_REWARD * (0.35 * time_relative + 0.65 * frontier_relative)
            - exploit_penalty,
            -MAX_FRONTIER_REWARD,
            MAX_FRONTIER_REWARD,
        )
        reward = unblended_reward
        if self.baseline_transition_remaining > 0:
            completed = BASELINE_TRANSITION_EPISODES - self.baseline_transition_remaining + 1
            progress = _clamp(completed / BASELINE_TRANSITION_EPISODES)
            reward = (
                (1.0 - progress) * self.baseline_transition_anchor_reward
                + progress * unblended_reward
            )
        self.generation_time_history.append(effective_time)
        self.frontier_growth_history.append(frontier_growth)
        target_time = max(1.0e-9, _mean(self.generation_time_history))
        target_frontier = max(1.0e-9, _mean(self.frontier_growth_history))
        alpha = 0.08 if self.baseline_transition_remaining > 0 else 0.20
        self.generation_time_baseline = (
            (1.0 - alpha) * max(1.0e-9, self.generation_time_baseline or target_time)
            + alpha * target_time
        )
        self.frontier_growth_baseline = (
            (1.0 - alpha) * max(1.0e-9, self.frontier_growth_baseline or target_frontier)
            + alpha * target_frontier
        )
        if self.baseline_transition_remaining > 0:
            self.baseline_transition_remaining -= 1
        self.last_frontier_reward = reward
        return {
            "generationTimeSeconds": self.episode_generation_seconds,
            "candidateEvaluations": self.episode_candidate_evaluations,
            "actionNormalizedGenerationTime": self.episode_action_normalized_seconds,
            "sizeNormalizedGenerationTime": effective_time,
            "meanModuleArea": mean_area,
            "generationTimeReferenceUsed": time_reference,
            "generationTimeBaseline": self.generation_time_baseline,
            "relativeGenerationTime": time_relative,
            "frontierGrowthPotential": frontier_growth,
            "frontierGrowthReferenceUsed": frontier_reference,
            "frontierGrowthBaseline": self.frontier_growth_baseline,
            "relativeFrontierGrowth": frontier_relative,
            "smallShapeRatio": small_ratio,
            "smallShapeExploitPenalty": exploit_penalty,
            "unblendedRelativeTimeReward": unblended_reward,
            "relativeTimeReward": reward,
            "baselineTransitionEpisodes": self.baseline_transition_remaining,
        }

    @staticmethod
    def _resample_loop(poly: Sequence[dict], sample_count: int) -> list[dict[str, float]]:
        """Sample a polygon at equal perimeter intervals for a fixed-size vector signature."""

        if not poly or sample_count <= 0:
            return []
        lengths = [
            math.hypot(
                poly[(index + 1) % len(poly)]["x"] - point["x"],
                poly[(index + 1) % len(poly)]["y"] - point["y"],
            )
            for index, point in enumerate(poly)
        ]
        perimeter = math.fsum(lengths)
        if perimeter <= 1.0e-9:
            return [
                {"x": float(poly[0]["x"]), "y": float(poly[0]["y"])}
                for _ in range(sample_count)
            ]
        samples: list[dict[str, float]] = []
        edge_index = 0
        edge_start = 0.0
        for sample_index in range(sample_count):
            target = perimeter * sample_index / sample_count
            while (
                edge_index + 1 < len(poly)
                and target > edge_start + lengths[edge_index] + 1.0e-12
            ):
                edge_start += lengths[edge_index]
                edge_index += 1
            first = poly[edge_index]
            second = poly[(edge_index + 1) % len(poly)]
            length = max(1.0e-9, lengths[edge_index])
            ratio = _clamp((target - edge_start) / length)
            samples.append(
                {
                    "x": float(first["x"] + (second["x"] - first["x"]) * ratio),
                    "y": float(first["y"] + (second["y"] - first["y"]) * ratio),
                }
            )
        return samples

    @classmethod
    def _loop_signature(
        cls,
        poly: Sequence[dict],
        reference_center: dict,
        reference_scale: float,
    ) -> list[float]:
        """Represent the loop as a starting anchor + a sequence of pairwise displacement vectors."""

        sig_len = VECTOR_SIGNATURE_SAMPLES * 2 + 2
        if not poly:
            return [0.0] * sig_len
        scale = max(1.0e-8, float(reference_scale))
        samples = cls._resample_loop(poly, VECTOR_SIGNATURE_SAMPLES)
        
        centroid = G.polygon_centroid(poly)
        anchor = [
            _clamp((float(centroid["x"]) - float(reference_center["x"])) / scale, -1.5, 1.5),
            _clamp((float(centroid["y"]) - float(reference_center["y"])) / scale, -1.5, 1.5),
        ]
        
        vectors = []
        n = len(samples)
        for i in range(n):
            p1 = samples[i]
            p2 = samples[(i + 1) % n]
            
            dx = _clamp((float(p2["x"]) - float(p1["x"])) / scale, -1.5, 1.5)
            dy = _clamp((float(p2["y"]) - float(p1["y"])) / scale, -1.5, 1.5)
            
            vectors.extend([dx, dy])
            
        return anchor + vectors

    @classmethod
    def _vector_site_descriptor(
        cls,
        outer: Sequence[dict],
        holes: Sequence[Sequence[dict]],
        settings: dict[str, Any],
    ) -> list[float]:
        """Describe one floor without collapsing away its boundary or atrium vectors."""

        bounds = G.bounds_of(outer)
        width = float(bounds["maxX"] - bounds["minX"])
        height = float(bounds["maxY"] - bounds["minY"])
        scale = max(1.0, width, height)
        center = G.polygon_centroid(outer)
        outer_area = float(G.polygon_area(outer))
        hole_areas = [float(G.polygon_area(hole)) for hole in holes]
        hole_area = math.fsum(hole_areas)
        exact_area = max(0.0, outer_area - hole_area)
        outer_perimeter = float(G.polygon_perimeter(outer))
        inner_perimeter = math.fsum(G.polygon_perimeter(hole) for hole in holes)
        hull_area = float(G.polygon_area(G.convex_hull(outer)))
        convexity = _safe_ratio(outer_area, hull_area)
        outer_signature = cls._loop_signature(outer, center, scale)
        sig_len = VECTOR_SIGNATURE_SAMPLES * 2 + 2
        if holes and hole_area > 1.0e-9:
            hole_signatures = [cls._loop_signature(hole, center, scale) for hole in holes]
            hole_signature = [
                math.fsum(
                    signature[index] * area
                    for signature, area in zip(hole_signatures, hole_areas)
                )
                / hole_area
                for index in range(sig_len)
            ]
        else:
            hole_signature = [0.0] * sig_len
        scalars = [
            _clamp(exact_area / 1400.0),
            _clamp(outer_perimeter / 180.0),
            _clamp(inner_perimeter / 100.0),
            _clamp(width / 60.0),
            _clamp(height / 60.0),
            _clamp(_safe_ratio(hole_area, outer_area)),
            _clamp(convexity),
            _clamp(len(outer) / 24.0),
            _clamp(len(holes) / 4.0),
            1.0 if settings["singleFloor"] else 0.0,
            1.0 if settings["publicMode"] else 0.0,
            _clamp(float(settings["maxModules"]) / 300.0),
        ]
        descriptor = scalars + outer_signature + hole_signature
        if len(descriptor) != FLOOR_DESCRIPTOR_DIM:
            raise RuntimeError("floor descriptor dimension mismatch")
        return descriptor

    @staticmethod
    def _central_atrium_distance(boundary: dict, candidate: dict) -> float:
        boundary_center = G.polygon_centroid(boundary["outer"])
        return min(
            (
                math.hypot(
                    G.polygon_centroid(hole)["x"] - boundary_center["x"],
                    G.polygon_centroid(hole)["y"] - boundary_center["y"],
                )
                for hole in candidate.get("holes", [])
            ),
            default=math.inf,
        )

    def _choose_atrium(
        self,
        settings: dict[str, Any],
        boundary: dict,
        candidates: Sequence[dict],
    ) -> tuple[dict, torch.Tensor | None]:
        policy = settings["atriumPolicy"]
        none_choice = next((item for item in candidates if item["id"] == "none"), candidates[0])
        nonempty = [item for item in candidates if item.get("holes")]
        if policy == "none" or not nonempty:
            return none_choice, None
        if policy == "central":
            return min(
                nonempty,
                key=lambda item: (self._central_atrium_distance(boundary, item), str(item["id"])),
            ), None
        features = torch.tensor(
            [
                self._vector_site_descriptor(boundary["outer"], candidate.get("holes", []), settings)
                for candidate in candidates
            ],
            dtype=torch.float32,
            device=self.device,
        )
        logits = torch.nan_to_num(
            self.model.atrium_logits(features), nan=0.0, posinf=20.0, neginf=-20.0
        ).clamp(-30.0, 30.0)
        distribution = torch.distributions.Categorical(logits=logits)
        action = distribution.sample()
        return candidates[int(action.item())], distribution.log_prob(action)

    @staticmethod
    def _layout_offsets(site_records: Sequence[tuple[dict, dict, dict, G.RNG]]) -> list[tuple[float, float]]:
        count = len(site_records)
        columns = max(1, math.ceil(math.sqrt(count)))
        widths = []
        heights = []
        for _, _, site, _ in site_records:
            bounds = site["bounds"]
            widths.append(bounds["maxX"] - bounds["minX"])
            heights.append(bounds["maxY"] - bounds["minY"])
        column_width = max(widths, default=40.0) + 14.0
        row_height = max(heights, default=30.0) + 14.0
        return [((index % columns) * column_width, (index // columns) * row_height) for index in range(count)]

    def _build_sites(
        self,
        settings: dict[str, Any],
        generation_id: int,
    ) -> tuple[list[FloorEnvironment], list[torch.Tensor]]:
        records: list[tuple[dict, dict, dict, G.RNG]] = []
        atrium_log_probs: list[torch.Tensor] = []
        base_seed = int(settings["seed"]) + generation_id * 104729
        for index in range(int(settings["parallelEnvironments"])):
            rng = G.RNG(base_seed + index * 8191)
            boundary = G.make_boundary(settings["boundaryType"], rng.fork(11), settings)
            candidates = G.atrium_candidates(boundary, rng.fork(23))
            atrium, atrium_log_prob = self._choose_atrium(settings, boundary, candidates)
            if atrium_log_prob is not None:
                atrium_log_probs.append(atrium_log_prob)
            site = G.build_site(boundary, atrium.get("holes", []))
            records.append((boundary, atrium, site, rng.fork(53)))
        offsets = self._layout_offsets(records)
        return (
            [
                FloorEnvironment(index, boundary, atrium, site, offsets[index], rng)
                for index, (boundary, atrium, site, rng) in enumerate(records)
            ],
            atrium_log_probs,
        )

    @classmethod
    def _site_descriptor(
        cls,
        environments: Sequence[FloorEnvironment],
        settings: dict[str, Any],
    ) -> list[list[float]]:
        """Keep one vector descriptor row per floor for learned pooling."""

        return [
            cls._vector_site_descriptor(
                environment.site["outer"], environment.site["holes"], settings
            )
            for environment in environments
        ]

    @staticmethod
    def _canonical_module(module: dict, angle_step: float, phase: int) -> dict:
        """Attach sampled rotations to geometry's canonical connection walls."""

        result = copy.deepcopy(module)
        rotation_step = angle_step
        # A triangle has only one connection edge, unlike every other generated
        # module's opposing pair.  Preserve the useful meaning of a zero angle
        # increment while allowing the unavoidable triangular vocabulary at a
        # three-edge cap to flip onto an existing canonical wall.
        if angle_step <= 0.0 and len(result["poly"]) == 3:
            rotation_step = 180.0
        rotation_samples = 24
        if rotation_step > 0.0:
            rotation_samples = min(72, max(24, int(math.ceil(360.0 / rotation_step))))
        result["rotations"] = G.normalize_rotations(
            result["poly"], rotation_step, phase=phase, max_samples=rotation_samples
        )
        if not result["rotations"]:
            raise SettingsError(f"module {result['id']} has no usable rotations")
        return result

    def _synthesize_dictionary(
        self,
        settings: dict[str, Any],
        environments: Sequence[FloorEnvironment],
        generation_id: int,
        episode: int,
    ) -> tuple[list[dict], list[torch.Tensor]]:
        """Propose a dictionary through factorized discrete geometry actions."""

        cap = int(settings["dictCap"])
        floor_tensor = torch.tensor(
            self._site_descriptor(environments, settings), dtype=torch.float32, device=self.device
        )
        if floor_tensor.ndim != 2 or floor_tensor.shape[0] == 0:
            raise SettingsError("shape policy requires at least one floor descriptor")
        pooled_site = self.model.encode_sites(floor_tensor)
        category_logits = torch.nan_to_num(
            self.model.category_logits(pooled_site), nan=0.0, posinf=20.0, neginf=-20.0
        ).clamp(-30.0, 30.0)
        parameter_logits = tuple(
            torch.nan_to_num(logits, nan=0.0, posinf=20.0, neginf=-20.0).clamp(-30.0, 30.0)
            for logits in self.model.shape_parameter_logits(pooled_site)
        )
        
        # Multi-floor runs learn Core/Room vocabularies. Canonical single-floor
        # mode disables structural Core/Corridor classifications entirely.
        single_floor = bool(settings["singleFloor"])
        allowed_category_indices = [2] if single_floor else [0, 2]

        dictionary: list[dict] = []
        log_probs: list[torch.Tensor] = []
        
        core_count = 0 if single_floor else 1
        used_actions: set[tuple[int, int, int, int]] = set()
        
        epsilon = max(0.18, 0.65 * math.exp(-episode / 50.0))
        for slot_index in range(cap):
            if single_floor:
                category_index = 2  # Room
            elif slot_index == 0:
                category_index = 0  # Core
            elif slot_index == 1:
                category_index = 2  # Room
            else:
                active_category_indices = [2] if core_count >= 2 else allowed_category_indices
                subset = category_logits[active_category_indices]
                policy_probabilities = torch.softmax(subset, dim=0)
                behavior_probabilities = (
                    (1.0 - epsilon) * policy_probabilities
                    + epsilon * torch.full_like(policy_probabilities, 1.0 / len(active_category_indices))
                )
                category_distribution = torch.distributions.Categorical(probs=behavior_probabilities)
                category_action = category_distribution.sample()
                category_index = active_category_indices[int(category_action.item())]
                log_probs.append(category_distribution.log_prob(category_action))
                if category_index == 0:
                    core_count += 1
                        
            category = MODULE_CATEGORIES[category_index]

            all_proposals = G.enumerate_parametric_proposals(settings, category)
            unused = [
                proposal
                for proposal in all_proposals
                if (
                    proposal["widthIndex"],
                    proposal["heightIndex"],
                    proposal["angleIndex"],
                    proposal["typeIndex"],
                )
                not in used_actions
            ]
            proposals = unused or all_proposals
            if dictionary:
                existing_areas = [float(item["area"]) for item in dictionary]
                def ratio_is_safe(proposal: dict) -> bool:
                    candidate_areas = existing_areas + [float(proposal["area"])]
                    return max(candidate_areas) / max(1.0e-9, min(candidate_areas)) <= 5.0 + 1.0e-8

                ratio_safe = [proposal for proposal in proposals if ratio_is_safe(proposal)]
                if not ratio_safe:
                    # Reusing a safe action is preferable to violating the
                    # architectural 5:1 size invariant.
                    ratio_safe = [proposal for proposal in all_proposals if ratio_is_safe(proposal)]
                proposals = ratio_safe
            if not proposals:
                raise SettingsError(f"no valid dynamic-palette proposals for {category}")

            proposal_indices = torch.tensor(
                [
                    [
                        proposal["widthIndex"],
                        proposal["heightIndex"],
                        proposal["angleIndex"],
                        proposal["typeIndex"],
                    ]
                    for proposal in proposals
                ],
                dtype=torch.long,
                device=self.device,
            )
            proposal_logits = (
                parameter_logits[0][proposal_indices[:, 0]]
                + parameter_logits[1][proposal_indices[:, 1]]
                + parameter_logits[2][proposal_indices[:, 2]]
                + parameter_logits[3][proposal_indices[:, 3]]
            )
            shape_policy_probabilities = torch.softmax(proposal_logits, dim=0)
            shape_behavior_probabilities = (
                (1.0 - epsilon) * shape_policy_probabilities
                + epsilon * torch.full_like(shape_policy_probabilities, 1.0 / len(proposals))
            )
            shape_distribution = torch.distributions.Categorical(probs=shape_behavior_probabilities)
            shape_action = shape_distribution.sample()
            log_probs.append(shape_distribution.log_prob(shape_action))
            proposal = proposals[int(shape_action.item())]
            action_key = (
                proposal["widthIndex"],
                proposal["heightIndex"],
                proposal["angleIndex"],
                proposal["typeIndex"],
            )
            used_actions.add(action_key)
            module = G.synthesize_parametric_module(
                settings,
                category,
                proposal["widthIndex"],
                proposal["heightIndex"],
                proposal["angleIndex"],
                proposal["typeIndex"],
                f"s{slot_index}",
            )
            
            dictionary.append(
                self._canonical_module(
                    module, float(settings["angleStep"]), phase=episode + slot_index
                )
            )
            
        return dictionary, log_probs

    def _prepare_generation(
        self,
        settings: dict[str, Any],
        generation_id: int,
        episode: int,
    ) -> tuple[list[FloorEnvironment], list[dict], list[torch.Tensor]]:
        environments, atrium_logs = self._build_sites(settings, generation_id)
        dictionary, shape_logs = self._synthesize_dictionary(
            settings, environments, generation_id, episode
        )
        for environment in environments:
            environment.reset(dictionary)
        return environments, dictionary, atrium_logs + shape_logs

    def _commit_generation(
        self,
        settings: dict[str, Any],
        generation_id: int,
        environments: list[FloorEnvironment],
        dictionary: list[dict],
        shape_logs: list[torch.Tensor],
    ) -> None:
        next_reward_signature = (
            self._reward_signature(settings),
            self._reward_site_fingerprint(environments),
            self._reward_dictionary_fingerprint(dictionary),
        )
        if (
            next_reward_signature != self.reward_settings_signature
            and self.generation_time_baseline is not None
        ):
            # Preserve the old reference and ease it toward the new workload;
            # this avoids a one-episode reward spike after a structural edit.
            self.baseline_transition_remaining = BASELINE_TRANSITION_EPISODES
            self.baseline_transition_anchor_reward = self.last_frontier_reward
        self.reward_settings_signature = next_reward_signature
        self.settings = settings
        self.generation_id = generation_id
        self.environments = environments
        self.dictionary = dictionary
        self.shape_log_probs = shape_logs
        self.placement_log_probs = []
        self.step_number = 0
        self._reset_episode_reward_telemetry()
        for group in self.optimizer.param_groups:
            group["lr"] = float(settings["learningRate"])

    def update_settings(self, patch: Any) -> dict[str, Any]:
        """Validate, prepare, and atomically commit settings plus a fresh site."""

        proposed = validate_settings_patch(self.settings, patch)
        generation = self.generation_id + 1
        environments, dictionary, shape_logs = self._prepare_generation(proposed, generation, self.episode)
        self._commit_generation(proposed, generation, environments, dictionary, shape_logs)
        return self.site_event()

    def new_site(self) -> dict[str, Any]:
        """Atomically replace local sites while preserving learned policy state."""

        generation = self.generation_id + 1
        environments, dictionary, shape_logs = self._prepare_generation(
            self.settings, generation, self.episode
        )
        self._commit_generation(self.settings, generation, environments, dictionary, shape_logs)
        return self.site_event()

    def reset_policy(self) -> dict[str, Any]:
        """Reset all learned state, then atomically publish a fresh generation."""

        old_model = self.model
        old_optimizer = self.optimizer
        old_episode = self.episode
        self.model = PolicyModel().to(self.device)
        self.optimizer = optim.Adam(self.model.parameters(), lr=float(self.settings["learningRate"]))
        try:
            self.episode = 0
            generation = self.generation_id + 1
            environments, dictionary, shape_logs = self._prepare_generation(
                self.settings, generation, self.episode
            )
        except Exception:
            self.model = old_model
            self.optimizer = old_optimizer
            self.episode = old_episode
            raise
        self.baseline = 0.35
        self.score_history = []
        self.best_score = 0.0
        self.topology_multiplier = 0.05
        self.step_profiler.reset()
        self.last_loss = 0.0
        self.generation_time_history.clear()
        self.frontier_growth_history.clear()
        self.generation_time_baseline = None
        self.frontier_growth_baseline = None
        self.baseline_transition_remaining = 0
        self.baseline_transition_anchor_reward = 0.0
        self.last_frontier_reward = 0.0
        self._commit_generation(self.settings, generation, environments, dictionary, shape_logs)
        return self.site_event()

    def _aggregate_online(self) -> dict[str, Any]:
        per_site = [environment.online_metrics() for environment in self.environments]
        filled = math.fsum(float(item["filledArea"]) for item in per_site)
        site_area = math.fsum(float(item["siteArea"]) for item in per_site)
        rentable = math.fsum(float(item["rentableArea"]) for item in per_site)
        module_count = sum(int(item["moduleCount"]) for item in per_site)
        repeated = math.fsum(float(item["reuseRatio"]) * int(item["moduleCount"]) for item in per_site)
        fill_ratio = _safe_ratio(filled, site_area)
        rentable_ratio = _safe_ratio(rentable, filled)
        reuse_ratio = _safe_ratio(repeated, module_count)
        score = 100.0 * _clamp(0.56 * fill_ratio + 0.36 * rentable_ratio + 0.08 * reuse_ratio)
        return {
            "filledArea": filled,
            "siteArea": site_area,
            "fillRatio": fill_ratio,
            "averageFill": fill_ratio,
            "rentableArea": rentable,
            "rentableRatio": rentable_ratio,
            "averageRentable": rentable_ratio,
            "reuseRatio": reuse_ratio,
            "moduleCount": module_count,
            "dictionaryLength": len(self.dictionary),
            "daylightRatio": 0.0,
            "score": score,
            "perSite": per_site,
        }

    def site_event(self) -> dict[str, Any]:
        return {
            "type": "site",
            "generationId": self.generation_id,
            "episode": self.episode,
            "device": self.device.type,
            "boundaries": [environment.world_boundary() for environment in self.environments],
            "dictionary": [_public_module(module) for module in self.dictionary],
            "metrics": self._aggregate_online(),
            "scoreHistory": list(self.score_history),
            "bestScore": float(self.best_score),
        }

    def _aggregate_terminal(self, per_site: Sequence[dict[str, Any]]) -> dict[str, Any]:
        filled = math.fsum(float(item["filledArea"]) for item in per_site)
        site_area = math.fsum(float(item["siteArea"]) for item in per_site)
        rentable = math.fsum(float(item["rentableArea"]) for item in per_site)
        module_count = sum(int(item["moduleCount"]) for item in per_site)
        perimeter = math.fsum(float(item["exposedPerimeter"]) for item in per_site)
        fill_ratio = _safe_ratio(filled, site_area)
        rentable_ratio = _safe_ratio(rentable, filled)
        daylight = _safe_ratio(
            math.fsum(float(item["daylightRatio"]) * float(item["rentableArea"]) for item in per_site),
            rentable,
        )
        envelope_daylight = _safe_ratio(
            math.fsum(
                float(item["envelopeDaylightRatio"]) * float(item["rentableArea"])
                for item in per_site
            ),
            rentable,
        )
        reuse = _safe_ratio(
            math.fsum(float(item["reuseRatio"]) * int(item["moduleCount"]) for item in per_site),
            module_count,
        )
        constructibility = _safe_ratio(
            math.fsum(float(item["constructibilityScore"]) * float(item["filledArea"]) for item in per_site),
            filled,
        )
        envelope_efficiency = _safe_ratio(
            math.fsum(float(item["envelopeEfficiency"]) * float(item["filledArea"]) for item in per_site),
            filled,
        )
        exterior_corridor = _mean([float(item["exteriorCorridorRatio"]) for item in per_site])
        triangle_ratio = _safe_ratio(
            math.fsum(float(item["triangleRatio"]) * float(item["filledArea"]) for item in per_site),
            filled,
        )
        invalid_sites = [item for item in per_site if not item["topologyValid"]]
        violation_count = sum(len(item["topologyViolations"]) for item in per_site)
        violation_rate = _clamp(
            _safe_ratio(len(invalid_sites), len(per_site))
            + 0.08 * _safe_ratio(violation_count, max(1, len(per_site)))
        )

        # Piecewise linear scaling for fill ratio (< 60% penalized heavily)
        scaled_fill = max(0.0, 2.25 * fill_ratio - 0.75) if fill_ratio < 0.6 else fill_ratio

        # Piecewise linear scaling for rentable ratio (< 70% penalized heavily)
        scaled_rentable = max(0.0, (7.0 * rentable_ratio - 2.8) / 3.0) if rentable_ratio < 0.7 else rentable_ratio

        # Normalized area variance penalty of dictionary shapes (Coefficient of Variation CV = std / mean, max 0.15)
        dict_areas = [G.polygon_area(m["poly"]) for m in self.dictionary]
        mean_dict_area = _mean(dict_areas) if dict_areas else 1.0
        cv = _safe_ratio(_std(dict_areas), max(1.0, mean_dict_area)) if dict_areas else 0.0
        area_variance_penalty = _clamp(0.05 * cv, 0.0, 0.15)

        # Note: self.site["outer"] represents the site property boundary, NOT an architectural exterior wall.
        # The outer perimeter of the union of placed shapes forms the actual building exterior facade walls.
        # Internal partition walls are shared edges between adjacent modules.
        internal_exposed_penalty = 0.0

        # Partial connection penalty (incentivizes full edge connections)
        total_partial_len = math.fsum(float(item.get("totalPartialLength", 0.0)) for item in per_site)
        partial_connection_penalty = 0.04 * _safe_ratio(total_partial_len, perimeter)

        raw_score = 100.0 * min(
            1.0,
            0.70 * scaled_fill
            + 0.15 * scaled_rentable
            + 0.10 * daylight
            + 0.02 * reuse
            + 0.02 * constructibility
            + 0.01 * envelope_efficiency
            - area_variance_penalty
            - partial_connection_penalty,
        )
        multiplier_used = self.topology_multiplier
        topology_penalty = min(50.0, 100.0 * multiplier_used * violation_rate)
        score = min(raw_score - topology_penalty, 100.0)
        self.topology_multiplier = _clamp(
            self.topology_multiplier + 0.004 * (violation_rate - 0.02), 0.05, 0.15
        )
        violations = [
            f"floor{item['instanceIdx']}:{violation}"
            for item in per_site
            for violation in item["topologyViolations"]
        ]
        return {
            "filledArea": filled,
            "siteArea": site_area,
            "fillRatio": fill_ratio,
            "averageFill": fill_ratio,
            "rentableArea": rentable,
            "rentableRatio": rentable_ratio,
            "averageRentable": rentable_ratio,
            "daylightRatio": daylight,
            "siteDaylightRatio": daylight,
            "envelopeDaylightRatio": envelope_daylight,
            "reuseRatio": reuse,
            "moduleCount": module_count,
            "dictionaryLength": len(self.dictionary),
            "exposedPerimeter": perimeter,
            "perimeters": [float(item["exposedPerimeter"]) for item in per_site],
            "envelopeEfficiency": envelope_efficiency,
            "constructibilityScore": constructibility,
            "lightScore": daylight,
            "exteriorCorridorRatio": exterior_corridor,
            "triangleRatio": triangle_ratio,
            "topologyValid": not invalid_sites,
            "topologyViolations": violations,
            "topologyViolationRate": violation_rate,
            "topologyPenalty": topology_penalty,
            "topologyMultiplier": multiplier_used,
            "nextTopologyMultiplier": self.topology_multiplier,
            "rawScore": raw_score,
            "areaVariancePenalty": area_variance_penalty * 100.0,
            "internalExposedPenalty": internal_exposed_penalty * 100.0,
            "partialConnectionPenalty": partial_connection_penalty * 100.0,
            "score": score,
            "perSite": list(per_site),
        }

    def _learn_from_episode(self, score: float) -> None:
        normalized_score = score / 100.0
        advantage = _clamp(normalized_score - self.baseline, -0.6, 0.6)
        terms: list[torch.Tensor] = []
        if self.placement_log_probs:
            terms.append(torch.stack(self.placement_log_probs).mean())
        if self.shape_log_probs:
            terms.append(0.8 * torch.stack(self.shape_log_probs).mean())
        if terms:
            self.optimizer.zero_grad(set_to_none=True)
            loss = -advantage * torch.stack(terms).sum()
            loss.backward()
            nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=2.0)
            self.optimizer.step()
            self.last_loss = float(loss.detach().cpu().item())
        self.baseline = 0.90 * self.baseline + 0.10 * normalized_score

    def _finish_episode(self) -> dict[str, Any]:
        t_episode_start = time.perf_counter()
        completed_episode = self.episode
        t_term_metrics_start = time.perf_counter()
        per_site = [
            environment.terminal_metrics(
                bool(self.settings["singleFloor"]), float(self.settings["coreSpacing"])
            )
            for environment in self.environments
        ]
        self.step_profiler.record("terminalMetrics", time.perf_counter() - t_term_metrics_start)
        
        t_agg_term_start = time.perf_counter()
        metrics = self._aggregate_terminal(per_site)
        self.step_profiler.record("aggregateTerminal", time.perf_counter() - t_agg_term_start)
        
        # 1. Run BPE merging
        t_ep_bpe_start = time.perf_counter()
        layout_graphs = []
        for idx, environment in enumerate(self.environments):
            layout_graphs.append(graph.extract_layout_graph(environment.placements, idx))
            
        merged_vocab, bpe_stats = graph.bpe_merge(
            layout_graphs,
            min_frequency=2,
            max_rounds=20,
            max_vocab_size=30
        )
        self.step_profiler.record("episodeBpeMerge", time.perf_counter() - t_ep_bpe_start)
        reused_bpe_modules, bpe_bonus = _reused_bpe_module_summary(layout_graphs)
            
        # Count top-level post-merge triangles from polygon geometry, then apply
        # the canonical -8 points per average unmerged triangle per floor.
        post_merge_triangles = graph.count_post_merge_triangles(layout_graphs)
        unmerged_triangles = len(post_merge_triangles)
        unmerged_triangle_penalty = _average_unmerged_triangle_penalty(
            unmerged_triangles, len(layout_graphs)
        )

        # 2. Apply BPE bonus and unmerged triangle penalty to score (allow negative values for RL advantage gradients)
        frontier_metrics = self._relative_frontier_reward()
        score = (
            float(metrics["score"])
            + bpe_bonus
            - unmerged_triangle_penalty
            + float(frontier_metrics["relativeTimeReward"])
        )
        metrics["score"] = f"{score:.4f}"
        metrics["vocabSize"] = bpe_stats["unique_types"]
        metrics["totalPlacements"] = bpe_stats["total_placements"]
        metrics["bpeRounds"] = bpe_stats["merge_rounds"]
        metrics["reusedBpeModules"] = reused_bpe_modules
        metrics["bpeBonus"] = bpe_bonus
        metrics["unmergedTriangles"] = unmerged_triangles
        metrics["averageUnmergedTriangles"] = unmerged_triangles / max(1, len(layout_graphs))
        metrics["unmergedTrianglePenalty"] = unmerged_triangle_penalty
        metrics.update(frontier_metrics)
        
        # 3. Learn from updated score
        t_learning_start = time.perf_counter()
        self._learn_from_episode(score)
        self.step_profiler.record("learning", time.perf_counter() - t_learning_start)
        metrics["policyLoss"] = self.last_loss
        metrics["baseline"] = self.baseline
        self.score_history.append(score)
        self.best_score = max(self.best_score, score)

        completed_dictionary_formatted = [
            _public_module(module) for module in self.dictionary
        ]
        individual_placements_formatted = []
        for env_idx, environment in enumerate(self.environments):
            dx, dy = environment.offset
            for placement in environment.placements:
                world_poly = G.translate_polygon(placement["poly"], dx, dy)
                individual_placements_formatted.append({
                    "id": placement["id"],
                    "poly": world_poly,
                    "instanceIdx": env_idx,
                    "center": G.polygon_centroid(world_poly),
                    "module": {
                        "id": placement["moduleId"],
                        "category": placement.get("category", "room"),
                    },
                })

        self.episode += 1
        t_dict_start = time.perf_counter()
        next_dictionary, next_shape_logs = self._synthesize_dictionary(
            self.settings, self.environments, self.generation_id, self.episode
        )
        self.step_profiler.record("dictSynthesis", time.perf_counter() - t_dict_start)
        self.dictionary = next_dictionary
        self.shape_log_probs = next_shape_logs
        self.placement_log_probs = []
        self.step_number = 0
        for environment in self.environments:
            environment.reset(next_dictionary)
        self._reset_episode_reward_telemetry()
            
        # 4. Format merged placements for rendering
        t_ep_format_start = time.perf_counter()
        merged_placements_formatted = []
        for env_idx, layout_graph in enumerate(layout_graphs):
            environment = self.environments[env_idx]
            dx, dy = environment.offset
            for node in layout_graph.nodes.values():
                category = node.get("category", "room")
                if "shapeType" in node and node["shapeType"].startswith("M_round"):
                    category = "room"
                poly = node["poly"]
                world_poly = G.translate_polygon(poly, dx, dy)
                
                components_formatted = []
                if "components" in node:
                    for comp in node["components"]:
                        comp_world_poly = G.translate_polygon(comp["poly"], dx, dy)
                        components_formatted.append({
                            "id": comp["id"],
                            "poly": comp_world_poly,
                            "instanceIdx": env_idx,
                            "center": G.polygon_centroid(comp_world_poly),
                            "module": {
                                "id": comp.get("shapeType", comp.get("moduleId", comp["id"])),
                                "category": comp.get("category", "room"),
                            }
                        })
                else:
                    components_formatted.append({
                        "id": node["id"],
                        "poly": world_poly,
                        "instanceIdx": env_idx,
                        "center": G.polygon_centroid(world_poly),
                        "module": {
                            "id": node.get("shapeType", node.get("moduleId", node["id"])),
                            "category": category,
                        }
                    })
                    
                merged_placements_formatted.append({
                    "id": node["id"],
                    "poly": world_poly,
                    "instanceIdx": env_idx,
                    "center": G.polygon_centroid(world_poly),
                    "module": {
                        "id": node.get("shapeType", node.get("moduleId", node["id"])),
                        "category": category,
                    },
                    "components": components_formatted
                })
                
        self.step_profiler.record("episodeFormatting", time.perf_counter() - t_ep_format_start)
        
        ep_duration = (time.perf_counter() - self.episode_start_time) if self.episode_start_time is not None else (time.perf_counter() - t_episode_start)
        self.step_profiler.record("episodeTotal", ep_duration)
        self.episode_start_time = None
        
        metrics["performanceTimings"] = self.step_profiler.summary()

        return {
            "type": "episodeDone",
            "generationId": self.generation_id,
            "completedEpisode": completed_episode,
            "nextEpisode": self.episode,
            "metrics": metrics,
            "scoreHistory": list(self.score_history),
            "bestScore": self.best_score,
            "dictionary": completed_dictionary_formatted,
            "nextDictionary": [_public_module(module) for module in next_dictionary],
            "mergedDictionary": [_public_merged_module(module) for module in merged_vocab],
            "placements": individual_placements_formatted,
            "mergedPlacements": merged_placements_formatted,
        }

    def step(self, generation_id: Any, episode: Any) -> dict[str, Any]:
        """Advance every active floor with one batched placement-policy call."""
        if self.episode_start_time is None:
            self.episode_start_time = time.perf_counter()
        t_step_start = time.perf_counter()

        if (
            isinstance(generation_id, bool)
            or isinstance(episode, bool)
            or not isinstance(generation_id, int)
            or not isinstance(episode, int)
            or generation_id != self.generation_id
            or episode != self.episode
        ):
            raise StaleStepError(
                f"step targets generation {generation_id}, episode {episode}; "
                f"active run is generation {self.generation_id}, episode {self.episode}"
            )
        if not self.environments:
            raise RuntimeError("create a site before stepping")
        if all(environment.done for environment in self.environments):
            return self._finish_episode()

        angle_step = float(self.settings["angleStep"])
        orientation_basis = 0.0 if angle_step <= 0.0 else (self.episode * angle_step * 3.0) % 180.0
        candidate_groups: list[tuple[FloorEnvironment, list[PlacementCandidate]]] = []
        all_features: list[list[float]] = []
        # Keep the shared action batch bounded as the number of floors grows.
        # Twelve exact actions per floor preserve enough geometric diversity
        # for each environment to reach its requested episode cap.
        per_environment_limit = max(12, 48 // max(1, len(self.environments)))
        active_envs = [
            env for env in self.environments 
            if not env.done and len(env.placements) < int(self.settings["maxModules"])
        ]
        
        def _gen(env: FloorEnvironment) -> tuple[FloorEnvironment, list[PlacementCandidate], float]:
            g_start = time.perf_counter()
            cands = env.generate_candidates(
                self.settings, orientation_basis, limit=per_environment_limit, profiler=self.step_profiler
            )
            return env, cands, time.perf_counter() - g_start

        if len(active_envs) > 1:
            gen_results = list(self.executor.map(_gen, active_envs))
        else:
            gen_results = [_gen(env) for env in active_envs]

        for environment, candidates, gen_duration in gen_results:
            self._record_frontier_sample(environment, gen_duration)
            if not candidates:
                environment.done = True
                continue
            candidate_groups.append((environment, candidates))
            all_features.extend(candidate.features for candidate in candidates)

        if not candidate_groups:
            return self._finish_episode()

        feature_tensor = torch.tensor(all_features, dtype=torch.float32, device=self.device)
        t_inference_start = time.perf_counter()
        logits = torch.nan_to_num(
            self.model.placement_logits(feature_tensor), nan=0.0, posinf=20.0, neginf=-20.0
        ).clamp(-30.0, 30.0)
        self.step_profiler.record("policyInference", time.perf_counter() - t_inference_start)
        temperature = max(0.32, 0.90 * math.exp(-self.episode / 45.0))
        placements: list[dict] = []
        cursor = 0
        t_placement_start = time.perf_counter()
        for environment, candidates in candidate_groups:
            group_logits = logits[cursor : cursor + len(candidates)] / temperature
            cursor += len(candidates)
            distribution = torch.distributions.Categorical(logits=group_logits)
            selected_index = distribution.sample()
            self.placement_log_probs.append(distribution.log_prob(selected_index))
            placement = environment.place(candidates[int(selected_index.item())])
            placements.append(placement)
            if len(environment.placements) >= int(self.settings["maxModules"]):
                environment.done = True
        self.step_profiler.record("placement", time.perf_counter() - t_placement_start)

        self.step_number += 1
        self.step_profiler.record("bpeMerge", 0.0)
        merged_placements_formatted = []
        merged_vocab = []

        metrics = self._aggregate_online()
        self.step_profiler.record("stepTotal", time.perf_counter() - t_step_start)
        metrics["performanceTimings"] = self.step_profiler.summary()

        return {
            "type": "placements",
            "generationId": self.generation_id,
            "episode": self.episode,
            "step": self.step_number,
            "placements": placements,
            "mergedPlacements": merged_placements_formatted,
            "mergedDictionary": [_public_merged_module(module) for module in merged_vocab],
            "metrics": metrics,
        }

    def evaluate(self, generation_id: str, episode: int) -> dict[str, Any]:
        """Perform a complete terminal-like evaluation of the current placements without state mutation."""
        if generation_id != self.generation_id or episode != self.episode:
            raise StaleStepError("evaluation is stale")

        # 1. Compute BPE merges
        layout_graphs = []
        for idx, environment in enumerate(self.environments):
            layout_graphs.append(graph.extract_layout_graph(environment.placements, idx))
            
        merged_vocab, bpe_stats = graph.bpe_merge(
            layout_graphs,
            min_frequency=2,
            max_rounds=20,
            max_vocab_size=30
        )
        
        # 2. Compute terminal metrics
        single_floor = self.settings.get("singleFloor", False)
        core_spacing = float(self.settings.get("coreSpacing", 8.0))
        per_site = [
            environment.terminal_metrics(single_floor, core_spacing)
            for environment in self.environments
        ]
        metrics = self._aggregate_terminal(per_site)
        
        # 3. Calculate BPE bonus and triangle penalties
        reused_bpe_modules, bpe_bonus = _reused_bpe_module_summary(layout_graphs)
            
        # Count post-merge triangles using actual polygon geometry (same logic as _finish_episode)
        post_merge_triangles = graph.count_post_merge_triangles(layout_graphs)
        unmerged_triangles = len(post_merge_triangles)
        unmerged_triangle_penalty = _average_unmerged_triangle_penalty(
            unmerged_triangles, len(layout_graphs)
        )
        
        score = float(metrics["score"]) + bpe_bonus - unmerged_triangle_penalty
        metrics["score"] = f"{score:.4f}"
        metrics["vocabSize"] = bpe_stats["unique_types"]
        metrics["totalPlacements"] = bpe_stats["total_placements"]
        metrics["bpeRounds"] = bpe_stats["merge_rounds"]
        metrics["reusedBpeModules"] = reused_bpe_modules
        metrics["bpeBonus"] = bpe_bonus
        metrics["unmergedTriangles"] = unmerged_triangles
        metrics["averageUnmergedTriangles"] = unmerged_triangles / max(1, len(layout_graphs))
        metrics["unmergedTrianglePenalty"] = unmerged_triangle_penalty
        
        # 4. Format BPE merged placements for rendering
        merged_placements_formatted = []
        for env_idx, layout_graph in enumerate(layout_graphs):
            environment = self.environments[env_idx]
            dx, dy = environment.offset
            for node in layout_graph.nodes.values():
                category = node.get("category", "room")
                if "shapeType" in node and node["shapeType"].startswith("M_round"):
                    category = "room"
                poly = node["poly"]
                world_poly = G.translate_polygon(poly, dx, dy)
                
                components_formatted = []
                if "components" in node:
                    for comp in node["components"]:
                        comp_world_poly = G.translate_polygon(comp["poly"], dx, dy)
                        components_formatted.append({
                            "id": comp["id"],
                            "poly": comp_world_poly,
                            "instanceIdx": env_idx,
                            "center": G.polygon_centroid(comp_world_poly),
                            "module": {
                                "id": comp.get("shapeType", comp.get("moduleId", comp["id"])),
                                "category": comp.get("category", "room"),
                            }
                        })
                else:
                    components_formatted.append({
                        "id": node["id"],
                        "poly": world_poly,
                        "instanceIdx": env_idx,
                        "center": G.polygon_centroid(world_poly),
                        "module": {
                            "id": node.get("shapeType", node.get("moduleId", node["id"])),
                            "category": category,
                        }
                    })
                    
                merged_placements_formatted.append({
                    "id": node["id"],
                    "poly": world_poly,
                    "instanceIdx": env_idx,
                    "center": G.polygon_centroid(world_poly),
                    "module": {
                        "id": node.get("shapeType", node.get("moduleId", node["id"])),
                        "category": category,
                    },
                    "components": components_formatted
                })
                
        # Format individual placements
        placements = []
        for env_idx, environment in enumerate(self.environments):
            dx, dy = environment.offset
            for placement in environment.placements:
                poly = placement["poly"]
                world_poly = G.translate_polygon(poly, dx, dy)
                placements.append({
                    "id": placement["id"],
                    "poly": world_poly,
                    "instanceIdx": env_idx,
                    "center": G.polygon_centroid(world_poly),
                    "module": {
                        "id": placement.get("shapeType", placement.get("moduleId", placement["id"])),
                        "category": placement.get("category", "room"),
                    }
                })

        return {
            "type": "placements",
            "generationId": self.generation_id,
            "episode": self.episode,
            "step": self.step_number,
            "placements": placements,
            "mergedPlacements": merged_placements_formatted,
            "mergedDictionary": [_public_merged_module(module) for module in merged_vocab],
            "metrics": metrics,
        }

    def save_checkpoint(self) -> str:
        """Persist the complete session policy state in a portable checkpoint."""

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        path = os.path.join(OUTPUT_DIR, "checkpoint.pt")
        cpu_state = {name: tensor.detach().cpu() for name, tensor in self.model.state_dict().items()}
        torch.save(
            {
                "version": 3,
                "model": cpu_state,
                "optimizer": self.optimizer.state_dict(),
                "settings": dict(self.settings),
                "generationId": self.generation_id,
                "episode": self.episode,
                "baseline": self.baseline,
                "scoreHistory": list(self.score_history),
                "bestScore": self.best_score,
                "topologyMultiplier": self.topology_multiplier,
            },
            path,
        )
        return path

    def load_checkpoint_data(self, data_bytes: bytes) -> dict[str, Any]:
        """Load session policy state from checkpoint binary data, and commit it."""
        import io
        checkpoint = torch.load(io.BytesIO(data_bytes), map_location=self.device)
        
        # Keep old states in case load fails
        old_model_state = self.model.state_dict()
        old_opt_state = self.optimizer.state_dict()
        old_settings = self.settings
        old_generation_id = self.generation_id
        old_episode = self.episode
        old_baseline = self.baseline
        old_score_history = self.score_history
        old_best_score = self.best_score
        old_topology_multiplier = self.topology_multiplier
        
        try:
            self.model.load_state_dict(checkpoint["model"])
            self.optimizer.load_state_dict(checkpoint["optimizer"])
            self.settings = validate_settings_patch(DEFAULT_SETTINGS, checkpoint.get("settings", {}))
            self.generation_id = checkpoint.get("generationId", 0)
            self.episode = checkpoint.get("episode", 0)
            self.baseline = checkpoint.get("baseline", 0.35)
            self.score_history = list(checkpoint.get("scoreHistory", []))
            self.best_score = checkpoint.get("bestScore", 0.0)
            self.topology_multiplier = checkpoint.get("topologyMultiplier", 0.08)
            
            # Prepare new generation using the loaded policy/settings
            generation = self.generation_id + 1
            environments, dictionary, shape_logs = self._prepare_generation(
                self.settings, generation, self.episode
            )
        except Exception:
            # Restore original state if anything failed
            self.model.load_state_dict(old_model_state)
            self.optimizer.load_state_dict(old_opt_state)
            self.settings = old_settings
            self.generation_id = old_generation_id
            self.episode = old_episode
            self.baseline = old_baseline
            self.score_history = old_score_history
            self.best_score = old_best_score
            self.topology_multiplier = old_topology_multiplier
            raise
            
        self._commit_generation(self.settings, generation, environments, dictionary, shape_logs)
        return self.site_event()



app = FastAPI(title="Module Lab v0.6-B")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def get_index() -> FileResponse:
    return FileResponse(os.path.join(BASE_DIR, "index.html"))


@app.get("/app.js")
async def get_app_js() -> FileResponse:
    return FileResponse(os.path.join(BASE_DIR, "app.js"))


@app.get("/styles.css")
async def get_styles_css() -> FileResponse:
    return FileResponse(os.path.join(BASE_DIR, "styles.css"))


def _error_event(
    trainer: ParallelTrainer,
    message: str,
    command: str | None = None,
    code: str = "server_error",
    recoverable: bool = True,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "type": "error",
        "code": code,
        "message": message,
        "generationId": trainer.generation_id,
        "episode": trainer.episode,
        "recoverable": recoverable,
    }
    if command:
        event["command"] = command
    return event


async def _send_json(websocket: WebSocket, event: dict[str, Any]) -> None:
    await websocket.send_text(json.dumps(event, allow_nan=False, separators=(",", ":")))


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Serve one isolated trainer; heavy mutations run outside the event loop."""

    await websocket.accept()
    trainer = ParallelTrainer()
    print(f"WebSocket trainer connected on device: {trainer.device.type}")
    await _send_json(websocket, trainer.site_event())
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await _send_json(websocket, _error_event(trainer, "message is not valid JSON", code="invalid_json"))
                continue
            if not isinstance(message, dict) or not isinstance(message.get("cmd"), str):
                await _send_json(
                    websocket,
                    _error_event(trainer, "message must contain a string cmd", code="invalid_command"),
                )
                continue
            command = message["cmd"]
            try:
                if command == "updateSettings":
                    site = await asyncio.to_thread(trainer.update_settings, message.get("settings"))
                    await _send_json(
                        websocket,
                        {
                            "type": "ack",
                            "command": command,
                            "message": "settings applied",
                            "generationId": trainer.generation_id,
                            "episode": trainer.episode,
                        },
                    )
                    await _send_json(websocket, site)
                elif command == "newSite":
                    site = await asyncio.to_thread(trainer.new_site)
                    await _send_json(websocket, site)
                elif command == "resetPolicy":
                    site = await asyncio.to_thread(trainer.reset_policy)
                    await _send_json(
                        websocket,
                        {
                            "type": "ack",
                            "command": command,
                            "message": "policy reset",
                            "generationId": trainer.generation_id,
                            "episode": trainer.episode,
                        },
                    )
                    await _send_json(websocket, site)
                elif command == "saveCheckpoint":
                    path = await asyncio.to_thread(trainer.save_checkpoint)
                    await _send_json(
                        websocket,
                        {
                            "type": "ack",
                            "command": command,
                            "message": f"checkpoint saved to {os.path.relpath(path, BASE_DIR)}",
                            "generationId": trainer.generation_id,
                            "episode": trainer.episode,
                        },
                    )
                elif command == "loadCheckpoint":
                    import base64
                    file_data = message.get("fileData")
                    if not file_data:
                        raise ValueError("No fileData provided in loadCheckpoint command")
                    data_bytes = base64.b64decode(file_data)
                    site = await asyncio.to_thread(trainer.load_checkpoint_data, data_bytes)
                    await _send_json(
                        websocket,
                        {
                            "type": "ack",
                            "command": command,
                            "message": "checkpoint loaded successfully",
                            "generationId": trainer.generation_id,
                            "episode": trainer.episode,
                        },
                    )
                    await _send_json(websocket, site)
                elif command == "step":
                    event = await asyncio.to_thread(
                        trainer.step, message.get("generationId"), message.get("episode")
                    )
                    await _send_json(websocket, event)
                elif command == "evaluate":
                    event = await asyncio.to_thread(
                        trainer.evaluate, message.get("generationId"), message.get("episode")
                    )
                    await _send_json(websocket, event)
                else:
                    await _send_json(
                        websocket,
                        _error_event(
                            trainer,
                            f"unknown command: {command}",
                            command=command,
                            code="unknown_command",
                        ),
                    )
            except StaleStepError as error:
                await _send_json(
                    websocket,
                    _error_event(
                        trainer, str(error), command=command, code="stale_generation", recoverable=True
                    ),
                )
            except SettingsError as error:
                await _send_json(
                    websocket,
                    _error_event(
                        trainer, str(error), command=command, code="invalid_settings", recoverable=True
                    ),
                )
            except Exception as error:
                print(f"{command} failed: {error}")
                await _send_json(
                    websocket,
                    _error_event(
                        trainer,
                        f"{command} failed: {error}",
                        command=command,
                        code="server_error",
                        recoverable=False,
                    ),
                )
    except WebSocketDisconnect:
        print("WebSocket trainer disconnected")


if __name__ == "__main__":
    print(f"Module Lab v0.6-B policy device: {select_device().type}")
    uvicorn.run(app, host="127.0.0.1", port=8000)
