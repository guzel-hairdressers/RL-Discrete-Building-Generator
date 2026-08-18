"""Module Lab v0.8.0 PyTorch training and WebSocket server.

Each WebSocket owns a completely independent :class:`ParallelTrainer`.  Within
that trainer all floor environments share one policy and one optimizer.  Shape
dictionary selection and placement selection are both stochastic policy
actions, so terminal aggregate reward trains the complete design policy.

Vector geometry is authoritative for containment, overlap, adjacency, exposed
walls, perimeter, and terminal daylight.  Integer cells are used only as a
candidate-search acceleration structure.

Multi-floor cores are exact building-level transactions: one learned action
selects a shared module, rotation, and local anchor for every floor.
"""

from __future__ import annotations

import asyncio
import collections
from collections import Counter, defaultdict, deque
import copy
import concurrent.futures
import ctypes
import heapq


import json
import math
import os
import re
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Iterable, Sequence
from urllib.parse import urlparse

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import uvicorn

import geometry as G
import graph


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "public"))
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
MIN_SHARED_EDGE = 0.5
MAX_CORRIDOR_WIDTH = 1.5
DAYLIGHT_DEPTH = 6.0
PLACEMENT_FEATURE_DIM = 22
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
MAX_CONSECUTIVE_PROPOSAL_FAILURES = 8
SECOND_CORE_MIN_ROOMS = 6
RELATIVE_TIME_WINDOW = 20
BASELINE_TRANSITION_EPISODES = 5
MAX_CHECKPOINT_BYTES = 64 * 1024 * 1024
MAX_FRONTIER_REWARD = 4.0
UNMERGED_TRIANGLE_PENALTY = 8.0
BPE_REUSE_BONUS_PER_MODULE = 1.5
CORE_STACK_CANDIDATE_LIMIT = 16
CORE_STACK_PROPOSAL_LIMIT = 512
CORE_SITE_TRANSACTION_ATTEMPTS = 24
BUILDING_TRAJECTORY_INDEX = -1
_TORCH_RUNTIME_LOCK = threading.Lock()
_TORCH_RUNTIME_CONFIGURED = False


DEFAULT_SETTINGS: dict[str, Any] = {
    "boundaryType": "free",
    "siteAreaTier": "ANY",
    "atriumPolicy": "none",
    "singleFloor": False,
    "publicMode": False,
    "parallelEnvironments": 4,
    "maxModules": 130,
    "learningRate": 0.001,
    "minEdge": 3.0,
    "maxEdge": 9.0,
    "dictCap": 10,
    "angleStep": 15.0,
    "coreSpacing": 8.0,
    "travelLimit": 12,
    "maxRoomHops": 3,
    "seed": 123,
    "allowCorridors": False,
    "allowStop": True,
    "beamSearchWidth": 1,
    "recordTrajectories": False,
}

BOUNDARY_TYPES = {"lobed", "lshape", "ushape", "tshape", "convex", "rect", "free"}
SITE_AREA_TIERS = {"ANY", "XS", "S", "M", "L", "XL"}
ATRIUM_POLICIES = {"central", "none"}


class SettingsError(ValueError):
    """Raised when a settings transaction is not valid in its entirety."""


class StaleStepError(RuntimeError):
    """Raised when stepping an inactive generation or episode."""


class CoreStackingError(RuntimeError):
    """Raised when an exact cross-floor core transaction cannot be prepared."""


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


def _max_cores_for_site(site_area: float) -> int:
    """Calculate dynamic core capacity scaling with site area (1 core per ~650-800 m²)."""
    return max(2, min(8, int(math.ceil(site_area / 650.0))))


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
    del episode  # Kept in the signature for checkpoint/API compatibility.
    bpe_bonus = min(30.0, float(BPE_REUSE_BONUS_PER_MODULE * reused_modules))
    return reused_modules, bpe_bonus


def validate_settings_patch(current: dict[str, Any], patch: Any) -> dict[str, Any]:
    """Validate a complete settings transaction without mutating *current*."""

    if not isinstance(patch, dict):
        raise SettingsError("settings must be an object")
    unknown = sorted(set(patch) - set(DEFAULT_SETTINGS) - {"maxEdges"})
    if unknown:
        raise SettingsError(f"unknown setting: {unknown[0]}")

    merged = dict(current)
    merged.update(patch)
    if "maxEdges" in merged:
        merged["maxEdges"] = int(
            _in_range(_integer(merged["maxEdges"], "maxEdges"), 3, 8, "maxEdges")
        )

    boundary_type = merged["boundaryType"]
    if not isinstance(boundary_type, str) or boundary_type not in BOUNDARY_TYPES:
        raise SettingsError("boundaryType is not supported")
    site_area_tier = merged["siteAreaTier"]
    if not isinstance(site_area_tier, str) or site_area_tier not in SITE_AREA_TIERS:
        raise SettingsError("siteAreaTier is not supported")
    atrium_policy = merged["atriumPolicy"]
    if not isinstance(atrium_policy, str) or atrium_policy not in ATRIUM_POLICIES:
        raise SettingsError("atriumPolicy is not supported")
    for key in ("singleFloor", "publicMode", "allowCorridors", "allowStop", "recordTrajectories"):
        if key in merged and type(merged[key]) is not bool:
            raise SettingsError(f"{key} must be a boolean")

    if "beamSearchWidth" in merged:
        merged["beamSearchWidth"] = int(
            _in_range(_integer(merged["beamSearchWidth"], "beamSearchWidth"), 1, 16, "beamSearchWidth")
        )

    merged["parallelEnvironments"] = int(
        _in_range(_integer(merged["parallelEnvironments"], "parallelEnvironments"), 1, 16, "parallelEnvironments")
    )
    merged["maxModules"] = int(
        _in_range(_integer(merged["maxModules"], "maxModules"), 10, 300, "maxModules")
    )
    merged["dictCap"] = int(
        _in_range(_integer(merged["dictCap"], "dictCap"), 3, 20, "dictCap")
    )
    merged["travelLimit"] = int(
        _in_range(_integer(merged["travelLimit"], "travelLimit"), 5, 60, "travelLimit")
    )
    merged["maxRoomHops"] = int(
        _in_range(_integer(merged.get("maxRoomHops", 3), "maxRoomHops"), 1, 10, "maxRoomHops")
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
        _finite_number(merged["learningRate"], "learningRate"), 0.0001, 0.05, "learningRate"
    )
    if not merged.get("singleFloor", False):
        basic_edge_count = 4
        maximum_core_area = (
            basic_edge_count
            * merged["maxEdge"] ** 2
            / (4.0 * math.tan(math.pi / basic_edge_count))
        )
        if maximum_core_area + 1.0e-8 < 24.0:
            raise SettingsError("maxEdge cannot form the required 24m² minimum core")
    return merged


def _validated_checkpoint_settings(settings: Any, version: int) -> dict[str, Any]:
    """Migrate historical settings into the current safe learner envelope."""

    if not isinstance(settings, dict):
        raise SettingsError("checkpoint settings must be an object")
    migrated = dict(settings)
    if version < 4:
        if "learningRate" in migrated:
            legacy_rate = _finite_number(migrated["learningRate"], "learningRate")
            migrated["learningRate"] = min(0.05, max(0.0001, legacy_rate))
        preview = dict(DEFAULT_SETTINGS)
        preview.update(migrated)
        if not bool(preview.get("singleFloor", False)):
            edge_count = min(int(preview["maxEdges"]), 4)
            required_edge = math.sqrt(
                24.0 * 4.0 * math.tan(math.pi / edge_count) / edge_count
            )
            migrated["maxEdge"] = max(
                float(preview["maxEdge"]), math.ceil(required_edge * 2.0 - 1.0e-9) / 2.0
            )
    return validate_settings_patch(DEFAULT_SETTINGS, migrated)


def _capture_torch_rng_state() -> dict[str, Any]:
    """Capture CPU and available accelerator generators for checkpointing."""

    state: dict[str, Any] = {"cpu": torch.random.get_rng_state().cpu()}
    if torch.cuda.is_available():
        state["cuda"] = [value.cpu() for value in torch.cuda.get_rng_state_all()]
    mps = getattr(torch, "mps", None)
    if mps is not None and hasattr(mps, "get_rng_state"):
        try:
            state["mps"] = mps.get_rng_state().cpu()
        except RuntimeError:
            pass
    return state


def _restore_torch_rng_state(state: Any, device: torch.device) -> None:
    """Restore generators available on this host; ignore foreign accelerators."""

    if not isinstance(state, dict) or not isinstance(state.get("cpu"), torch.Tensor):
        raise ValueError("checkpoint RNG state is invalid")
    torch.random.set_rng_state(state["cpu"].detach().cpu())
    if device.type == "cuda" and torch.cuda.is_available():
        cuda_states = state.get("cuda")
        if isinstance(cuda_states, (list, tuple)) and cuda_states:
            device_index = device.index if device.index is not None else torch.cuda.current_device()
            source_index = min(device_index, len(cuda_states) - 1)
            if isinstance(cuda_states[source_index], torch.Tensor):
                torch.cuda.set_rng_state(cuda_states[source_index].detach().cpu(), device=device)
    elif device.type == "mps":
        mps = getattr(torch, "mps", None)
        mps_state = state.get("mps")
        if mps is not None and hasattr(mps, "set_rng_state") and isinstance(mps_state, torch.Tensor):
            mps.set_rng_state(mps_state.detach().cpu())


def _safe_checkpoint_loading_supported() -> bool:
    """PyTorch 2.6 fixes CVE-2025-32434 in the weights-only loader."""

    match = re.match(r"^(\d+)\.(\d+)", str(torch.__version__))
    return bool(match and (int(match.group(1)), int(match.group(2))) >= (2, 6))


def _validate_adam_state_shapes(
    optimizer: optim.Adam, expected_learning_rate: float | None = None
) -> None:
    """Reject Adam state that loads successfully but cannot take a later step.

    Checkpoints may vary the learning rate through the public settings, but this
    project never enables Adam's alternative execution modes or hyperparameters.
    Requiring that canonical configuration avoids accepting individually valid
    flags whose combinations fail only on the next optimizer step.
    """

    allowed_group_keys = {
        "params",
        "lr",
        "betas",
        "eps",
        "weight_decay",
        "amsgrad",
        "maximize",
        "foreach",
        "capturable",
        "differentiable",
        "fused",
        "decoupled_weight_decay",
    }
    known_parameters: set[torch.Tensor] = set()
    for group in optimizer.param_groups:
        if not isinstance(group, dict) or set(group) - allowed_group_keys:
            raise ValueError("checkpoint optimizer parameter group is invalid")
        parameters = group.get("params")
        if not isinstance(parameters, list) or not all(
            isinstance(parameter, torch.Tensor) for parameter in parameters
        ):
            raise ValueError("checkpoint optimizer parameter list is invalid")
        known_parameters.update(parameters)
        for key in ("lr", "eps", "weight_decay"):
            value = group.get(key)
            if type(value) not in (int, float) or not math.isfinite(float(value)):
                raise ValueError(f"checkpoint optimizer {key} is invalid")
        if not 0.0 < float(group["lr"]) <= 0.05:
            raise ValueError("checkpoint optimizer learning rate is out of range")
        if expected_learning_rate is not None and not math.isclose(
            float(group["lr"]), float(expected_learning_rate), rel_tol=1e-12, abs_tol=0.0
        ):
            raise ValueError("checkpoint optimizer learning rate disagrees with settings")
        if float(group["eps"]) != 1e-8 or float(group["weight_decay"]) != 0.0:
            raise ValueError("checkpoint optimizer hyperparameters are unsupported")
        betas = group.get("betas")
        if not isinstance(betas, (list, tuple)) or len(betas) != 2:
            raise ValueError("checkpoint optimizer betas are invalid")
        if any(type(beta) not in (int, float) for beta in betas) or tuple(
            float(beta) for beta in betas
        ) != (0.9, 0.999):
            raise ValueError("checkpoint optimizer betas are unsupported")
        for key in ("amsgrad", "maximize", "capturable", "differentiable"):
            if group.get(key, False) is not False:
                raise ValueError(f"checkpoint optimizer {key} mode is unsupported")
        for key in ("foreach", "fused"):
            if group.get(key) is not None:
                raise ValueError(f"checkpoint optimizer {key} mode is unsupported")
        if group.get("decoupled_weight_decay", False) is not False:
            raise ValueError("checkpoint optimizer decoupled weight decay is unsupported")

        for parameter in group["params"]:
            state = optimizer.state.get(parameter, {})
            if not isinstance(state, dict):
                raise ValueError("checkpoint optimizer parameter state is invalid")
            if not state:
                continue
            required = {"step", "exp_avg", "exp_avg_sq"}
            if bool(group.get("amsgrad", False)):
                required.add("max_exp_avg_sq")
            if set(state) != required:
                raise ValueError("checkpoint optimizer moment state is incomplete")
            step = state["step"]
            if (
                not isinstance(step, torch.Tensor)
                or step.layout != torch.strided
                or step.numel() != 1
                or step.dtype not in (torch.float32, torch.float64)
                or step.device.type != "cpu"
            ):
                raise ValueError("checkpoint optimizer step state is invalid")
            if not bool(torch.isfinite(step).all()) or float(step.detach().cpu()) < 0.0:
                raise ValueError("checkpoint optimizer step state is invalid")
            for key in required - {"step"}:
                value = state[key]
                if not isinstance(value, torch.Tensor) or value.layout != torch.strided:
                    raise ValueError(f"checkpoint optimizer {key} state is invalid")
                if tuple(value.shape) != tuple(parameter.shape):
                    raise ValueError(
                        f"checkpoint optimizer {key} shape {tuple(value.shape)} "
                        f"does not match parameter shape {tuple(parameter.shape)}"
                    )
                if value.dtype != parameter.dtype or value.device != parameter.device:
                    raise ValueError(f"checkpoint optimizer {key} dtype/device is invalid")

    if any(parameter not in known_parameters for parameter in optimizer.state):
        raise ValueError("checkpoint optimizer contains orphan parameter state")


def select_device() -> torch.device:
    """Choose a portable policy device, with an explicit multi-GPU override."""

    requested = os.environ.get("MODULE_LAB_DEVICE", "auto").strip().lower()
    if requested == "cpu":
        return torch.device("cpu")
    if requested == "mps":
        mps_backend = getattr(torch.backends, "mps", None)
        if mps_backend is None or not mps_backend.is_available():
            raise RuntimeError("MODULE_LAB_DEVICE=mps requested, but MPS is unavailable")
        return torch.device("mps")
    if requested == "cuda" or requested.startswith("cuda:"):
        if not torch.cuda.is_available():
            raise RuntimeError(f"MODULE_LAB_DEVICE={requested} requested, but CUDA is unavailable")
        device = torch.device(requested)
        if device.index is not None and device.index >= torch.cuda.device_count():
            raise RuntimeError(f"CUDA device index {device.index} is unavailable")
        return device
    if requested != "auto":
        raise RuntimeError("MODULE_LAB_DEVICE must be auto, cpu, mps, cuda, or cuda:N")
    if torch.cuda.is_available():
        return torch.device("cuda")
    # Tiny scalar policy batches are generally faster on Apple Silicon CPU;
    # MPS remains available through the explicit override for larger studies.
    return torch.device("cpu")


def _configure_torch_runtime(device: torch.device) -> None:
    """Avoid large thread-pool overhead for the policy's tiny CPU tensors."""

    global _TORCH_RUNTIME_CONFIGURED
    if device.type != "cpu":
        return
    with _TORCH_RUNTIME_LOCK:
        if _TORCH_RUNTIME_CONFIGURED:
            return
        requested = os.environ.get("MODULE_LAB_TORCH_THREADS", "1")
        try:
            thread_count = max(1, min(8, int(requested)))
        except ValueError:
            thread_count = 1
        torch.set_num_threads(thread_count)
        try:
            torch.set_num_interop_threads(1)
        except RuntimeError:
            # An embedding host may already have initialized the pool.
            pass
        _TORCH_RUNTIME_CONFIGURED = True


class EquivariantRelationalSetTransformer(nn.Module):
    """SE(2)-Equivariant Relational Set Attention Transformer (Phase 1H).
    
    Computes pairwise relative invariant edge features (RBF Euclidean distance
    d_ij and relative normal orientation Δθ_ij = (cos Δθ, sin Δθ)) to enable cross-candidate
    spatial coordination across all building wings with exact mathematical invariance
    under 2D Euclidean rotations and translations.
    """

    def __init__(
        self,
        node_dim: int = PLACEMENT_FEATURE_DIM,
        hidden_dim: int = 64,
        num_heads: int = 4,
        num_layers: int = 2,
        num_rbf: int = 8,
        rbf_max_dist: float = 80.0,
    ) -> None:
        super().__init__()
        self.hidden_dim = hidden_dim
        self.num_heads = num_heads
        self.num_layers = num_layers
        self.num_rbf = num_rbf
        self.rbf_max_dist = rbf_max_dist

        self.node_proj = nn.Sequential(
            nn.Linear(node_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.SiLU(),
        )

        rbf_centers = torch.linspace(0.0, rbf_max_dist, num_rbf)
        self.register_buffer("rbf_centers", rbf_centers)
        self.rbf_sigma = rbf_max_dist / max(1, num_rbf - 1)

        edge_dim = num_rbf + 2
        self.edge_mlp = nn.Sequential(
            nn.Linear(edge_dim, hidden_dim // 2),
            nn.SiLU(),
            nn.Linear(hidden_dim // 2, num_heads),
        )

        self.q_proj = nn.ModuleList(
            [nn.Linear(hidden_dim, hidden_dim) for _ in range(num_layers)]
        )
        self.k_proj = nn.ModuleList(
            [nn.Linear(hidden_dim, hidden_dim) for _ in range(num_layers)]
        )
        self.v_proj = nn.ModuleList(
            [nn.Linear(hidden_dim, hidden_dim) for _ in range(num_layers)]
        )
        self.out_proj = nn.ModuleList(
            [nn.Linear(hidden_dim, hidden_dim) for _ in range(num_layers)]
        )
        self.norm1 = nn.ModuleList(
            [nn.LayerNorm(hidden_dim) for _ in range(num_layers)]
        )

        self.ffn = nn.ModuleList(
            [
                nn.Sequential(
                    nn.Linear(hidden_dim, hidden_dim * 2),
                    nn.SiLU(),
                    nn.Linear(hidden_dim * 2, hidden_dim),
                )
                for _ in range(num_layers)
            ]
        )
        self.norm2 = nn.ModuleList(
            [nn.LayerNorm(hidden_dim) for _ in range(num_layers)]
        )

        self.score_head = nn.Sequential(
            nn.Linear(hidden_dim, 32),
            nn.SiLU(),
            nn.Linear(32, 1),
        )

    def _compute_edge_features(
        self,
        positions: torch.Tensor,
        angles: torch.Tensor,
    ) -> torch.Tensor:
        diff_pos = positions.unsqueeze(1) - positions.unsqueeze(0)
        dist = torch.norm(diff_pos, dim=-1)
        rbf = torch.exp(
            -((dist.unsqueeze(-1) - self.rbf_centers) ** 2)
            / (2.0 * (self.rbf_sigma**2))
        )

        diff_angle = angles.unsqueeze(1) - angles.unsqueeze(0)
        cos_diff = torch.cos(diff_angle)
        sin_diff = torch.sin(diff_angle)
        angle_feats = torch.stack([cos_diff, sin_diff], dim=-1)

        return torch.cat([rbf, angle_feats], dim=-1)

    def forward(
        self,
        features: torch.Tensor,
        positions: torch.Tensor | None = None,
        angles: torch.Tensor | None = None,
    ) -> torch.Tensor:
        K = features.shape[0]
        h = self.node_proj(features)

        if K <= 1 or positions is None or angles is None:
            return self.score_head(h).squeeze(-1)

        edge_feats = self._compute_edge_features(positions, angles)
        edge_bias = self.edge_mlp(edge_feats).permute(2, 0, 1)

        head_dim = self.hidden_dim // self.num_heads
        scale = 1.0 / math.sqrt(head_dim)

        for l in range(self.num_layers):
            q = self.q_proj[l](h).view(K, self.num_heads, head_dim).permute(1, 0, 2)
            k = self.k_proj[l](h).view(K, self.num_heads, head_dim).permute(1, 0, 2)
            v = self.v_proj[l](h).view(K, self.num_heads, head_dim).permute(1, 0, 2)

            attn_scores = torch.bmm(q, k.transpose(1, 2)) * scale + edge_bias
            attn_weights = F.softmax(attn_scores, dim=-1)

            attn_out = (
                torch.bmm(attn_weights, v)
                .permute(1, 0, 2)
                .contiguous()
                .view(K, self.hidden_dim)
            )
            attn_out = self.out_proj[l](attn_out)
            h = self.norm1[l](h + attn_out)

            ffn_out = self.ffn[l](h)
            h = self.norm2[l](h + ffn_out)

        return self.score_head(h).squeeze(-1)


class PolicyModel(nn.Module):
    """Shared placement, vector-geometry, category, and atrium policy."""

    @staticmethod
    def _new_value_head() -> nn.Sequential:
        return nn.Sequential(
            nn.Linear(POOLED_SITE_DIM, 32),
            nn.SiLU(),
            nn.Linear(32, 1),
        )

    def __init__(self) -> None:
        super().__init__()
        self.transformer = EquivariantRelationalSetTransformer(
            node_dim=PLACEMENT_FEATURE_DIM,
            hidden_dim=64,
            num_heads=4,
            num_layers=2,
        )
        self.placement_head = self.transformer
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
        self.num_edges_head = nn.Linear(64, 2) # Edges 3 or 4 (triangles or quads)
        self.edge_length_heads = nn.ModuleList([nn.Linear(64, len(G.EDGE_PALETTE)) for _ in range(3)])
        self.angle_heads = nn.ModuleList([nn.Linear(64, len(G.ANGLE_PALETTE)) for _ in range(2)])
        # Preserve the baseline actor's initialization and subsequent sampling
        # stream: the critic is additive state, not an accidental RNG shift in
        # the policy experiment.
        rng_state = torch.random.get_rng_state()
        self.value_head = self._new_value_head()
        torch.random.set_rng_state(rng_state)

    def reset_value_head(self) -> None:
        """Replace critic parameters without perturbing the actor RNG stream."""

        rng_state = torch.random.get_rng_state()
        try:
            fresh_state = self._new_value_head().state_dict()
        finally:
            torch.random.set_rng_state(rng_state)
        self.value_head.load_state_dict(fresh_state)

    def placement_logits(
        self,
        features: torch.Tensor,
        positions: torch.Tensor | None = None,
        angles: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """Score candidate set using SE(2)-equivariant relational self-attention."""

        return self.transformer(features, positions, angles)

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

    def value(self, pooled_site: torch.Tensor) -> torch.Tensor:
        """Predict the normalized terminal return for Monte Carlo baselining."""

        return self.value_head(pooled_site.reshape(1, -1)).squeeze()

    def shape_parameter_logits(self, pooled_site: torch.Tensor) -> tuple[torch.Tensor, ...]:
        """Score num_edges, edge lengths, and internal angles."""

        features = self.shape_head(pooled_site.reshape(1, -1)).squeeze(0)
        return (
            self.num_edges_head(features),
            *(head(features) for head in self.edge_length_heads),
            *(head(features) for head in self.angle_heads),
        )


_DATACLASS_SLOTS = {"slots": True} if sys.version_info >= (3, 10) else {}


@dataclass(**_DATACLASS_SLOTS)
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
    anchor_x: float = 0.0
    anchor_y: float = 0.0


@dataclass(**_DATACLASS_SLOTS)
class CoreStackCandidate:
    """One exact module/rotation/local-anchor action valid on every floor."""

    module: dict
    rotation: dict
    anchor_x: float
    anchor_y: float
    floor_candidates: list[PlacementCandidate]

    @property
    def signature(self) -> tuple[str, float, float, float]:
        return (
            str(self.module["id"]),
            round(float(self.rotation.get("angle", 0.0)), 6),
            round(float(self.anchor_x), 6),
            round(float(self.anchor_y), 6),
        )

    @property
    def features(self) -> list[float]:
        return _mean_feature_rows(candidate.features for candidate in self.floor_candidates)


@dataclass(**_DATACLASS_SLOTS)
class PlacementPolicyDecision:
    """Detached ragged categorical data, recomputed once during learning."""

    environment_index: int
    features: torch.Tensor
    action_index: int
    temperature: float
    old_log_prob: float = 0.0
    positions: torch.Tensor | None = None
    angles: torch.Tensor | None = None



def record_dataset_trajectory(
    event: dict[str, Any],
    data_dir: str = "data",
    filename: str = "dataset_v1.jsonl",
) -> str | None:
    """Record completed multi-floor building episode to JSONL dataset."""
    if not isinstance(event, dict) or event.get("type") != "episodeDone":
        return None
    try:
        os.makedirs(data_dir, exist_ok=True)
        out_path = os.path.join(data_dir, filename)
        metrics_dict = event.get("metrics", {})
        score_raw = metrics_dict.get("score", metrics_dict.get("aggregateReward", 0.0))
        record = {
            "episode": event.get("completedEpisode", 0),
            "score": float(score_raw),
            "metrics": metrics_dict,
            "dictionary": event.get("dictionary", []),
            "mergedDictionary": event.get("mergedDictionary", []),
            "placements": event.get("placements", []),
            "mergedPlacements": event.get("mergedPlacements", []),
            "timestamp": time.time(),
        }
        with open(out_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        return out_path
    except Exception:
        return None


def _mean(values: Sequence[float]) -> float:
    return math.fsum(values) / len(values) if values else 0.0


def _mean_feature_rows(rows: Iterable[Sequence[float]]) -> list[float]:
    """Pool equal-width action features without changing their model contract."""

    materialized = [list(row) for row in rows]
    if not materialized:
        return [0.0] * PLACEMENT_FEATURE_DIM
    if any(len(row) != PLACEMENT_FEATURE_DIM for row in materialized):
        raise CoreStackingError("core-stack feature width does not match the placement policy")
    return [
        math.fsum(row[column] for row in materialized) / len(materialized)
        for column in range(PLACEMENT_FEATURE_DIM)
    ]


def _std(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    average = _mean(values)
    return math.sqrt(math.fsum((value - average) ** 2 for value in values) / len(values))


def _safe_ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator > 1.0e-9 else 0.0


def _mean_trajectory_log_probability(
    grouped_log_probabilities: dict[int, Sequence[torch.Tensor]],
) -> torch.Tensor | None:
    """Sum decisions within a rollout, then weight each rollout equally."""

    trajectories = [
        torch.stack(list(log_probabilities)).sum()
        for _, log_probabilities in sorted(grouped_log_probabilities.items())
        if log_probabilities
    ]
    return torch.stack(trajectories).mean() if trajectories else None


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
        self.consecutive_proposal_failures = 0
        self.attachment_query_cursor = 0

    def reset(self, dictionary: Sequence[dict]) -> None:
        """Reset episode state while retaining the exact same local site."""

        self.dictionary = list(dictionary)
        self.slot_index = self._build_slot_index(self.dictionary)
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
        self.consecutive_proposal_failures = 0
        self.attachment_query_cursor = 0

    @classmethod
    def _build_slot_index(cls, dictionary: list[dict]) -> dict[int, list[dict]]:
        slot_index = collections.defaultdict(list)
        for module in dictionary:
            for rotation in module["rotations"]:
                poly = rotation["poly"]
                p_len = len(poly)
                for e_idx in range(p_len):
                    p1 = poly[e_idx]
                    p2 = poly[(e_idx + 1) % p_len]
                    dx = p2["x"] - p1["x"]
                    dy = p2["y"] - p1["y"]
                    e_len = math.hypot(dx, dy)
                    if e_len < MIN_SHARED_EDGE:
                        continue
                    angle_key = cls._attachment_angle_key(p1, p2)
                    slot_index[angle_key].append({
                        "module": module,
                        "rotation": rotation,
                        "edgeIndex": e_idx,
                        "p1": p1,
                        "p2": p2,
                        "dx": dx,
                        "dy": dy,
                        "length": e_len,
                    })
        return dict(slot_index)


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
            for neighbor in self.adjacency_map.get(identifier, ()):
                increment = 1 if self.placement_by_id[neighbor]["category"] == "room" else 0
                new_cost = crossings + increment
                if new_cost < best.get(neighbor, 10**9):
                    best[neighbor] = new_cost
                    heapq.heappush(queue, (new_cost, neighbor))
        return best

    def _new_room_reaches_core(
        self,
        neighbors: Sequence[str],
        room_core_costs: dict[str, int] | None = None,
        max_hops: int = 3,
    ) -> bool:
        """Check a new standard room without rebuilding a graph per candidate."""

        if not neighbors:
            return False
        if room_core_costs is not None:
            return any(
                neighbor in room_core_costs
                and room_core_costs[neighbor] + 1 <= max_hops
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
                return crossings <= max_hops
            if crossings > max_hops:
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
            0.0,
            0.0,
        ]

    def _candidate_from_anchor_reference(
        self,
        module: dict,
        rotation: dict,
        anchor_x: float,
        anchor_y: float,
        settings: dict[str, Any],
        orientation_basis: float,
        room_core_costs: dict[str, int],
    ) -> PlacementCandidate | None:
        site_bounds = self.site["bounds"]
        rot_bounds = rotation.get("bounds", G.bounds_of(rotation["poly"]))
        min_x = rot_bounds["minX"] + anchor_x
        max_x = rot_bounds["maxX"] + anchor_x
        min_y = rot_bounds["minY"] + anchor_y
        max_y = rot_bounds["maxY"] + anchor_y

        if (
            min_x < site_bounds["minX"] - 1e-6
            or max_x > site_bounds["maxX"] + 1e-6
            or min_y < site_bounds["minY"] - 1e-6
            or max_y > site_bounds["maxY"] + 1e-6
        ):
            return None

        poly = G.translate_polygon(rotation["poly"], anchor_x, anchor_y)
        bounds = {"minX": min_x, "maxX": max_x, "minY": min_y, "maxY": max_y}

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
        if has_overlap:
            return None
        if not G.polygon_inside_site(poly, self.site["outer"], self.site["holes"]):
            return None
        if len(poly) == 4 and not G.is_convex_polygon(poly):
            return None
        cells = G.rasterize_polygon(poly)
        if not cells or any(_cell_key(cell) not in self.site["cellSet"] for cell in cells):
            return None

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

        neighbors: list[str] = []
        shared_overlap = 0.0
        for placement in nearby:
            maximum_overlap = _max_shared_overlap(poly, placement["poly"])
            if maximum_overlap + 1.0e-8 >= MIN_SHARED_EDGE:
                neighbors.append(placement["id"])
                shared_overlap += G.get_shared_overlap(poly, placement["poly"])
        if self.placements and not neighbors and category != "core":
            return None
        max_hops = int(settings.get("maxRoomHops", 3))
        if category == "room" and self.placements:
            if self.core_ids and not self._new_room_reaches_core(
                neighbors, room_core_costs, max_hops=max_hops
            ):
                return None

        outer_exposure = G.get_shared_overlap(poly, self.site["outer"])
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
        return PlacementCandidate(
            module=module,
            rotation=rotation,
            poly=poly,
            cells=cells,
            neighbors=neighbors,
            shared_overlap=shared_overlap,
            outer_exposure=outer_exposure,
            features=features,
            anchor_x=float(anchor_x),
            anchor_y=float(anchor_y),
        )

    def _sample_attachment_ids(self, identifiers: Sequence[int]) -> list[int]:
        """Rotate a fixed-size stratified view over an angle bucket.

        The frontier cap remains the main speed bound, while repeated policy
        queries eventually expose older and newer residual edges instead of
        permanently hiding every edge after the newest twelve.
        """

        ordered = list(identifiers)
        count = len(ordered)
        if count <= ATTACHMENT_MATCH_LIMIT:
            return ordered
        offset = self.attachment_query_cursor % count
        self.attachment_query_cursor += 1
        rotated = ordered[offset:] + ordered[:offset]
        return [
            rotated[(index * count) // ATTACHMENT_MATCH_LIMIT]
            for index in range(ATTACHMENT_MATCH_LIMIT)
        ]

    def _edge_alignment_anchors(
        self,
        module: dict,
        rotation: dict,
        include_edge_id: bool = False,
    ) -> Iterable[tuple]:
        """Yield anchors from a bounded, angle-indexed exposed-edge frontier."""

        candidate_poly = rotation["poly"]
        angle_period = int(round(math.pi * ATTACHMENT_ANGLE_SCALE))
        poly_len = len(candidate_poly)
        for candidate_index in range(poly_len):
            candidate_first = candidate_poly[candidate_index]
            candidate_second = candidate_poly[(candidate_index + 1) % poly_len]
            candidate_dx = candidate_second["x"] - candidate_first["x"]
            candidate_dy = candidate_second["y"] - candidate_first["y"]
            candidate_length = math.hypot(candidate_dx, candidate_dy)
            if candidate_length < MIN_SHARED_EDGE:
                continue
            angle_key = self._attachment_angle_key(candidate_first, candidate_second)
            
            pref_ids: list[int] = []
            norm_ids: list[int] = []
            seen_eids: set[int] = set()
            for delta in (-2, -1, 0, 1, 2):
                lookup = (angle_key + delta) % angle_period
                eids = self.attachment_by_angle.get(lookup)
                if eids:
                    for eid in eids:
                        if eid in seen_eids:
                            continue
                        seen_eids.add(eid)
                        edge = self.attachment_edges.get(eid)
                        if edge is not None:
                            if edge["preferred"]:
                                pref_ids.append(eid)
                            else:
                                norm_ids.append(eid)

            pref_ids.sort(reverse=True)
            norm_ids.sort(reverse=True)
            prioritized = self._sample_attachment_ids(pref_ids + norm_ids)
            for edge_id in prioritized:
                edge = self.attachment_edges[edge_id]
                placed_first = edge["a"]
                placed_second = edge["b"]
                placed_dx = placed_second["x"] - placed_first["x"]
                placed_dy = placed_second["y"] - placed_first["y"]
                placed_length = edge["length"]
                placed_poly = self.placement_by_id[edge["placementId"]]["poly"]
                full_first = placed_poly[edge["edgeIndex"]]
                full_second = placed_poly[
                    (edge["edgeIndex"] + 1) % len(placed_poly)
                ]
                full_placed_length = math.hypot(
                    full_second["x"] - full_first["x"],
                    full_second["y"] - full_first["y"],
                )
                length_ratio = candidate_length / max(
                    full_placed_length, G.EPSILON
                )
                if not any(
                    abs(length_ratio - valid_ratio) < 5.0e-3
                    for valid_ratio in (0.5, 1.0, 2.0)
                ):
                    continue
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
        candidate_bounds = G.bounds_of(candidate_poly)
        nearby_placements = [
            self.placement_by_id[identifier]
            for identifier in self._nearby_placement_ids(candidate_bounds)
            if self._bounds_intersect(candidate_bounds, self.placement_bounds[identifier])
        ]
        for i, first in enumerate(candidate_poly):
            second = candidate_poly[(i + 1) % len(candidate_poly)]
            dx = second["x"] - first["x"]
            dy = second["y"] - first["y"]
            len_a = math.hypot(dx, dy)
            if len_a <= 1e-4:
                continue
            
            for placement in nearby_placements:
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
                                
        # 3. Enforce Minimum 45° Facade Crevice Clearance (Zero Needle Slits)
        min_cos = 0.70710678  # cos(45 degrees)
        for p_idx, p in enumerate(candidate_poly):
            p_prev = candidate_poly[(p_idx - 1) % len(candidate_poly)]
            p_next = candidate_poly[(p_idx + 1) % len(candidate_poly)]
            
            dx_prev = p_prev["x"] - p["x"]
            dy_prev = p_prev["y"] - p["y"]
            len_prev = math.hypot(dx_prev, dy_prev)
            
            dx_next = p_next["x"] - p["x"]
            dy_next = p_next["y"] - p["y"]
            len_next = math.hypot(dx_next, dy_next)
            
            if len_prev < 1e-4 or len_next < 1e-4:
                continue
            u_prev = (dx_prev / len_prev, dy_prev / len_prev)
            u_next = (dx_next / len_next, dy_next / len_next)
            
            for placement in nearby_placements:
                other_poly = placement["poly"]
                for q_idx, q in enumerate(other_poly):
                    dist_sq = (p["x"] - q["x"])**2 + (p["y"] - q["y"])**2
                    if dist_sq < 1e-4:
                        q_prev = other_poly[(q_idx - 1) % len(other_poly)]
                        q_next = other_poly[(q_idx + 1) % len(other_poly)]
                        
                        dqx_prev = q_prev["x"] - q["x"]
                        dqy_prev = q_prev["y"] - q["y"]
                        len_q_prev = math.hypot(dqx_prev, dqy_prev)
                        
                        dqx_next = q_next["x"] - q["x"]
                        dqy_next = q_next["y"] - q["y"]
                        len_q_next = math.hypot(dqx_next, dqy_next)
                        
                        if len_q_prev < 1e-4 or len_q_next < 1e-4:
                            continue
                        uq_prev = (dqx_prev / len_q_prev, dqy_prev / len_q_prev)
                        uq_next = (dqx_next / len_q_next, dqy_next / len_q_next)
                        
                        for uc in (u_prev, u_next):
                            for uo in (uq_prev, uq_next):
                                dot = uc[0] * uo[0] + uc[1] * uo[1]
                                # Reject acute diverging/converging facade slits strictly between ~0.5° and 44.5°
                                if dot > min_cos and dot < 0.9999:
                                    return False

        # 4. Enforce Minimum 1.2m Opposing Facade Clearance (Zero Impassable Cracks)
        for i in range(len(candidate_poly)):
            p1 = candidate_poly[i]
            p2 = candidate_poly[(i + 1) % len(candidate_poly)]
            dx = p2["x"] - p1["x"]
            dy = p2["y"] - p1["y"]
            edge_len = math.hypot(dx, dy)
            if edge_len < 0.8:
                continue
            ux = dx / edge_len
            uy = dy / edge_len
            nx = uy
            ny = -ux
            mid = {"x": 0.5 * (p1["x"] + p2["x"]), "y": 0.5 * (p1["y"] + p2["y"])}
            
            existing_segs = []
            for placement in nearby_placements:
                other_poly = placement["poly"]
                for j in range(len(other_poly)):
                    q1 = other_poly[j]
                    q2 = other_poly[(j + 1) % len(other_poly)]
                    existing_segs.append({"a": q1, "b": q2})
            
            t = G.ray_intersect_segments(mid, (nx, ny), existing_segs, min_dist=0.05, max_dist=1.2)
            if t is not None and t < 1.2:
                return False

        return True

    def generate_candidates_for_module(
        self,
        module: dict,
        settings: dict[str, Any],
        orientation_basis: float,
        profiler: Any | None = None,
        limit: int = 12,
        category_filter: Sequence[str] | None = None,
    ) -> list[PlacementCandidate]:
        """Generate legal actions specifically for a single module."""
        cg_sub_totals = {
            "cgAnchorSearch": 0.0,
            "cgOverlapCollisions": 0.0,
            "cgSiteBoundary": 0.0,
            "cgNeighborAnalysis": 0.0,
            "cgEdgeAlignment": 0.0,
            "cgFeatureExtraction": 0.0,
        }
        placing_first = not self.placements
        single_floor = bool(settings["singleFloor"])
        core_count = sum(1 for p in self.placements if p.get("category") == "core")
        room_count = sum(1 for p in self.placements if p.get("category") == "room")
        max_cores = _max_cores_for_site(float(self.site["exactArea"]))
        if placing_first:
            allowed_cats = ["room"] if single_floor else ["core"]
        else:
            allowed_cats = ["room"]
            min_rooms_for_next_core = SECOND_CORE_MIN_ROOMS * core_count
            if not single_floor and (
                core_count == 0
                or (core_count < max_cores and room_count >= min_rooms_for_next_core)
            ):
                allowed_cats.append("core")
        if category_filter is not None:
            permitted = set(category_filter)
            allowed_cats = [
                category for category in allowed_cats if category in permitted
            ]

        room_core_costs = self._room_crossing_costs_to_core() if self.core_ids else {}
        rotations = self.rng.shuffle(module["rotations"])
        candidates: list[PlacementCandidate] = []
        # Preserve the baseline policy's per-category action capacity while
        # still terminating one-category searches once that category is full.
        category_limit = max(8, int(limit))
        eligible_categories = [
            category
            for category in allowed_cats
            if category != "core" or float(module["area"]) + 1.0e-8 >= 24.0
        ]
        category_counts = {category: 0 for category in eligible_categories}
        seen = set()
        frontier = self._frontier_cells() if placing_first else []
        quota_met = False
        
        for category in eligible_categories:
            for rotation in rotations:
                anchors: Iterable[tuple[float, float, Any]]
                t_anchor = time.perf_counter()
                if placing_first:
                    rotation_cells = rotation["cells"][:8]
                    anchors = [
                        (target["x"] - cell["x"], target["y"] - cell["y"], None)
                        for target in frontier
                        for cell in rotation_cells
                    ]
                else:
                    anchors = list(self._edge_alignment_anchors(module, rotation, include_edge_id=True))
                cg_sub_totals["cgAnchorSearch"] += time.perf_counter() - t_anchor
                for anchor_x, anchor_y, edge_id in anchors:
                    signature = (
                        module["id"],
                        category,
                        round(float(rotation.get("angle", 0.0)), 6),
                        round(anchor_x, 6),
                        round(anchor_y, 6),
                    )
                    if signature in seen:
                        continue
                    seen.add(signature)
                    candidate = self._candidate_from_anchor(
                        module,
                        rotation,
                        anchor_x,
                        anchor_y,
                        settings,
                        orientation_basis,
                        room_core_costs,
                        placement_category=category,
                        cg_sub_totals=cg_sub_totals,
                    )
                    if candidate is not None:
                        t_align = time.perf_counter()
                        valid_alignment = placing_first or self._validate_edge_alignment(candidate.poly)
                        cg_sub_totals["cgEdgeAlignment"] += time.perf_counter() - t_align
                        if not valid_alignment or not self._materialize_candidate(
                            candidate, settings, orientation_basis
                        ):
                            continue
                        # Pad standard candidate features to 22 dimensions
                        feat = list(candidate.features)
                        if len(feat) == 20:
                            feat = feat + [0.0, 0.0]
                        candidate.features = feat
                        candidates.append(candidate)
                        category_counts[category] += 1
                        if all(count >= category_limit for count in category_counts.values()):
                            quota_met = True
                            break
                if quota_met:
                    break
            if quota_met:
                break
        if profiler is not None:
            for label, total_sec in cg_sub_totals.items():
                profiler.record(label, total_sec)
        return candidates

    def _candidate_from_anchor(
        self,
        module: dict,
        rotation: dict,
        anchor_x: float,
        anchor_y: float,
        settings: dict[str, Any],
        orientation_basis: float,
        room_core_costs: dict[str, int],
        placement_category: str = "room",
        cg_sub_totals: dict[str, float] | None = None,
    ) -> PlacementCandidate | None:
        effective_module = {**module, "category": placement_category}
        rotation_poly = rotation["poly"]
        rotation_bounds = rotation.get("bounds")
        if rotation_bounds is None:
            rotation_bounds = G.bounds_of(rotation_poly)
            rotation["bounds"] = rotation_bounds
        bounds = {
            "minX": rotation_bounds["minX"] + anchor_x,
            "maxX": rotation_bounds["maxX"] + anchor_x,
            "minY": rotation_bounds["minY"] + anchor_y,
            "maxY": rotation_bounds["maxY"] + anchor_y,
        }
        site_bounds = self.site["bounds"]
        if (
            bounds["minX"] < site_bounds["minX"] - SPATIAL_PADDING
            or bounds["maxX"] > site_bounds["maxX"] + SPATIAL_PADDING
            or bounds["minY"] < site_bounds["minY"] - SPATIAL_PADDING
            or bounds["maxY"] > site_bounds["maxY"] + SPATIAL_PADDING
        ):
            return None
        t_overlap = time.perf_counter()
        has_overlap = False
        nearby = []
        poly = G.translate_polygon(rotation_poly, anchor_x, anchor_y)
        if self.placements:
            nearby_ids = {
                identifier
                for identifier in self._nearby_placement_ids(bounds)
                if self._bounds_intersect(bounds, self.placement_bounds[identifier])
            }
            if nearby_ids:
                nearby = [self.placement_by_id[identifier] for identifier in nearby_ids]
                has_overlap = any(G.polygons_overlap(poly, placement["poly"]) for placement in nearby)
        if cg_sub_totals is not None: cg_sub_totals["cgOverlapCollisions"] += time.perf_counter() - t_overlap
        if has_overlap:
            return None


        poly = G.translate_polygon(rotation_poly, anchor_x, anchor_y)

        t_bounds = time.perf_counter()
        inside_site = G.polygon_inside_site(poly, self.site["outer"], self.site["holes"])
        if cg_sub_totals is not None: cg_sub_totals["cgSiteBoundary"] += time.perf_counter() - t_bounds
        if not inside_site:
            return None
        if len(poly) == 4 and not G.is_convex_polygon(poly):
            return None
        t_bounds2 = time.perf_counter()
        # Rasterization is deferred until every vector predicate succeeds.
        # Rejected proposals are the overwhelming majority of candidate work.
        cells: list[dict] = []
        valid_cells = True
        if cg_sub_totals is not None: cg_sub_totals["cgSiteBoundary"] += time.perf_counter() - t_bounds2
        if not valid_cells:
            return None

        category = placement_category
        if category == "corridor" and G.min_polygon_width(poly) > MAX_CORRIDOR_WIDTH + 1.0e-8:
            return None
        if category == "core" and float(module["area"]) + 1.0e-8 < 24.0:
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
            pair_overlap = G.get_shared_overlap(poly, placement["poly"])
            if pair_overlap + 1.0e-8 >= MIN_SHARED_EDGE:
                neighbors.append(placement["id"])
                shared_overlap += pair_overlap
        if self.placements and not neighbors and category != "core":
            return None
        max_hops = int(settings.get("maxRoomHops", 3))
        if category == "room" and self.placements:
            if self.core_ids and not self._new_room_reaches_core(
                neighbors, room_core_costs, max_hops=max_hops
            ):
                return None

        outer_exposure = G.get_shared_overlap(poly, self.site["outer"])
        if cg_sub_totals is not None:
            cg_sub_totals["cgNeighborAnalysis"] += time.perf_counter() - t_neigh
        t_feat = time.perf_counter()
        features = self._candidate_features(
            effective_module,
            rotation,
            poly,
            cells,
            neighbors,
            shared_overlap,
            outer_exposure,
            settings,
            orientation_basis,
        )
        if cg_sub_totals is not None: cg_sub_totals["cgFeatureExtraction"] += time.perf_counter() - t_feat
        return PlacementCandidate(
            module=effective_module,
            rotation=rotation,
            poly=poly,
            cells=cells,
            neighbors=neighbors,
            shared_overlap=shared_overlap,
            outer_exposure=outer_exposure,
            features=features,
            anchor_x=float(anchor_x),
            anchor_y=float(anchor_y),
        )

    def _materialize_candidate(
        self,
        candidate: PlacementCandidate,
        settings: dict[str, Any],
        orientation_basis: float,
    ) -> bool:
        """Rasterize only a legal shortlisted action and refresh its features."""

        cells = G.rasterize_polygon(candidate.poly)
        if not cells or any(_cell_key(cell) not in self.site["cellSet"] for cell in cells):
            return False
        candidate.cells = cells
        candidate.features = self._candidate_features(
            candidate.module,
            candidate.rotation,
            candidate.poly,
            cells,
            candidate.neighbors,
            candidate.shared_overlap,
            candidate.outer_exposure,
            settings,
            orientation_basis,
        )
        return True

    def generate_candidates(
        self,
        settings: dict[str, Any],
        orientation_basis: float = 0.0,
        limit: int = 12,
        profiler: Any | None = None,
        allow_core: bool = True,
    ) -> list[PlacementCandidate]:
        """Generate legal actions with exact vector contacts and bounded work."""
        cg_sub_totals = {
            "cgAnchorSearch": 0.0,
            "cgOverlapCollisions": 0.0,
            "cgSiteBoundary": 0.0,
            "cgNeighborAnalysis": 0.0,
            "cgEdgeAlignment": 0.0,
            "cgFeatureExtraction": 0.0,
        }

        placing_first = not self.placements
        self.last_candidate_evaluations = 0
        self.last_unique_frontier_count = 0
        single_floor = bool(settings["singleFloor"])
        modules = self.rng.shuffle(self.dictionary)

        core_count = sum(1 for p in self.placements if p.get("category") == "core")
        room_count = sum(1 for p in self.placements if p.get("category") == "room")
        max_cores = _max_cores_for_site(float(self.site["exactArea"]))
        if placing_first:
            allowed_cats = ["room"] if single_floor else ["core"]
        else:
            allowed_cats = ["room"]
            min_rooms_for_next_core = SECOND_CORE_MIN_ROOMS * core_count
            if not single_floor and (
                core_count == 0
                or (core_count < max_cores and room_count >= min_rooms_for_next_core)
            ):
                allowed_cats.append("core")
        if not allow_core:
            allowed_cats = [
                category for category in allowed_cats if category != "core"
            ]

        core_candidates: list[PlacementCandidate] = []
        room_candidates: list[PlacementCandidate] = []
        seen: set[tuple] = set()
        frontier = self._frontier_cells() if placing_first else []
        room_core_costs = self._room_crossing_costs_to_core() if self.core_ids else {}

        cat_limit = max(8, int(limit))
        checked_edges = set()
        successful_edges = set()
        early_break = False

        # Pass 1: Generate candidates for allowed categories
        if placing_first:
            for module in modules:
                rotations = self.rng.shuffle(module["rotations"])
                for category in allowed_cats:
                    if category == "core" and float(module["area"]) + 1.0e-8 < 24.0:
                        continue
                    for rotation in rotations:
                        rotation_cells = rotation["cells"][:8]
                        anchors = [
                            (target["x"] - cell["x"], target["y"] - cell["y"], None)
                            for target in frontier
                            for cell in rotation_cells
                        ]
                        for anchor_x, anchor_y, edge_id in anchors:
                            signature = (
                                module["id"],
                                category,
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
                                placement_category=category,
                                cg_sub_totals=cg_sub_totals,
                            )
                            if candidate is not None:
                                t_align = time.perf_counter()
                                valid_alignment = self._validate_edge_alignment(candidate.poly)
                                cg_sub_totals["cgEdgeAlignment"] += time.perf_counter() - t_align
                                if not valid_alignment or not self._materialize_candidate(
                                    candidate, settings, orientation_basis
                                ):
                                    continue
                                if category == "core":
                                    core_candidates.append(candidate)
                                else:
                                    room_candidates.append(candidate)
                                core_quota_met = "core" not in allowed_cats or len(core_candidates) >= cat_limit
                                room_quota_met = "room" not in allowed_cats or len(room_candidates) >= cat_limit
                                if core_quota_met and room_quota_met:
                                    early_break = True
                                    break
                        if early_break:
                            break
                    if early_break:
                        break
        else:
            if not hasattr(self, "slot_index") or self.slot_index is None:
                self.slot_index = self._build_slot_index(self.dictionary)
                
            angle_period = int(round(math.pi * ATTACHMENT_ANGLE_SCALE))
            max_hops = int(settings.get("maxRoomHops", 3))
            
            # Prioritized edge list
            pref_ids = []
            norm_ids = []
            for eid, edge in self.attachment_edges.items():
                if edge.get("preferred"):
                    pref_ids.append(eid)
                else:
                    norm_ids.append(eid)
            all_edge_ids = self._sample_attachment_ids(pref_ids + norm_ids)
            
            for edge_id in all_edge_ids:
                edge = self.attachment_edges.get(edge_id)
                if edge is None:
                    continue
                parent_id = edge["placementId"]
                parent_cost = room_core_costs.get(parent_id, 0)
                
                # Hop Horizon Gating
                if self.core_ids and parent_cost >= max_hops:
                    edge_allowed_cats = [c for c in allowed_cats if c == "core"]
                else:
                    edge_allowed_cats = allowed_cats
                if not edge_allowed_cats:
                    continue
                    
                p1 = edge["a"]
                p2 = edge["b"]
                dx = p2["x"] - p1["x"]
                dy = p2["y"] - p1["y"]
                placed_length = edge["length"]
                edge_angle_key = edge["angleKey"]
                
                placed_poly = self.placement_by_id[edge["placementId"]]["poly"]
                full_first = placed_poly[edge["edgeIndex"]]
                full_second = placed_poly[(edge["edgeIndex"] + 1) % len(placed_poly)]
                full_placed_length = math.hypot(full_second["x"] - full_first["x"], full_second["y"] - full_first["y"])
                
                checked_edges.add(edge_id)
                
                matched_tiles = []
                for delta in (-2, -1, 0, 1, 2):
                    lookup = (edge_angle_key + delta) % angle_period
                    matched_tiles.extend(self.slot_index.get(lookup, ()))
                    
                for tile in matched_tiles:
                    candidate_length = tile["length"]
                    length_ratio = candidate_length / max(full_placed_length, G.EPSILON)
                    if not any(abs(length_ratio - valid_ratio) < 5.0e-3 for valid_ratio in (0.5, 1.0, 2.0)):
                        continue
                    cross = dx * tile["dy"] - dy * tile["dx"]
                    if abs(cross) > 1.0e-7 * placed_length * candidate_length:
                        continue
                    dot = dx * tile["dx"] + dy * tile["dy"]
                    if dot >= 0.0:
                        continue
                        
                    module = tile["module"]
                    rotation = tile["rotation"]
                    mod_id = module["id"]
                    candidate_first = tile["p1"]
                    candidate_second = tile["p2"]
                    
                    for anchor_x, anchor_y in (
                        (p2["x"] - candidate_first["x"], p2["y"] - candidate_first["y"]),
                        (p1["x"] - candidate_second["x"], p1["y"] - candidate_second["y"]),
                    ):
                        for category in edge_allowed_cats:
                            if category == "core" and float(module["area"]) + 1.0e-8 < 24.0:
                                continue
                            signature = (
                                mod_id,
                                category,
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
                                placement_category=category,
                                cg_sub_totals=cg_sub_totals,
                            )
                            if candidate is None:
                                continue
                                
                            t_align = time.perf_counter()
                            valid_alignment = self._validate_edge_alignment(candidate.poly)
                            cg_sub_totals["cgEdgeAlignment"] += time.perf_counter() - t_align
                            if not valid_alignment or not self._materialize_candidate(
                                candidate, settings, orientation_basis
                            ):
                                continue
                                
                            if category == "core":
                                core_candidates.append(candidate)
                            else:
                                room_candidates.append(candidate)
                            successful_edges.add(edge_id)
                            
                            core_quota_met = "core" not in allowed_cats or len(core_candidates) >= cat_limit
                            room_quota_met = "room" not in allowed_cats or len(room_candidates) >= cat_limit
                            if core_quota_met and room_quota_met:
                                early_break = True
                                break
                        if early_break:
                            break
                    if early_break:
                        break
                if early_break:
                    break



        if (
            not placing_first
            and not early_break
            and len(self.dictionary) >= int(settings.get("dictCap", 10))
        ):
            # An edge that rejects the current vocabulary may still be the
            # exact port needed by a later learned/frontier-compatible shape.
            # Retire it only once no create-new action remains.
            unattachable_edges = checked_edges - successful_edges
            for edge_id in unattachable_edges:
                self._remove_attachment(edge_id)

        # Pass 2: If not placing_first and no candidates found, try remote core candidates if core is allowed
        if not placing_first and not room_candidates and not core_candidates and "core" in allowed_cats:
            unoccupied_cells = [cell for cell in self.site["cells"] if _cell_key(cell) not in self.occupied]
            distance = self.site.get("distance", {})
            core_frontier = sorted(unoccupied_cells, key=lambda cell: -float(distance.get(_cell_key(cell), 0)))[:64]
            
            for module in modules:
                if float(module["area"]) + 1.0e-8 < 24.0:
                    continue
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
                            "core",
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
                            placement_category="core",
                            cg_sub_totals=cg_sub_totals,
                        )
                        if candidate is not None:
                            t_align = time.perf_counter()
                            valid_alignment = self._validate_edge_alignment(candidate.poly)
                            cg_sub_totals["cgEdgeAlignment"] += time.perf_counter() - t_align
                            if not valid_alignment:
                                continue
                            if not self._materialize_candidate(candidate, settings, orientation_basis):
                                continue
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
        special_candidates = []
        if (
            not placing_first
            and len(self.placements) >= 2
            and bool(settings.get("allowStop", False))
        ):
            special_candidates.append(
                PlacementCandidate(
                    module={"id": "stop", "category": "special", "area": 0.0},
                    rotation={"angle": 0.0},
                    poly=[],
                    cells=[],
                    neighbors=[],
                    shared_overlap=0.0,
                    outer_exposure=0.0,
                    features=[0.0] * 20 + [1.0, 0.0],
                )
            )
        if (not placing_first or len(self.dictionary) == 0) and len(self.dictionary) < int(settings.get("dictCap", 10)):
            special_candidates.append(
                PlacementCandidate(
                    module={"id": "create_new", "category": "special", "area": 0.0},
                    rotation={"angle": 0.0},
                    poly=[],
                    cells=[],
                    neighbors=[],
                    shared_overlap=0.0,
                    outer_exposure=0.0,
                    features=[0.0] * 20 + [0.0, 1.0],
                )
            )
        if profiler is not None:
            for label, total_sec in cg_sub_totals.items():
                profiler.record(label, total_sec)
        return core_candidates[:cat_limit] + room_candidates[:cat_limit] + special_candidates

    def _stack_commit_checkpoint(self) -> dict[str, Any]:
        """Capture only placement-owned mutable indexes for an atomic stack commit.

        Boundaries, sites, dictionaries, RNGs, and model state are intentionally
        excluded.  A rollback therefore restores the exact affected floor state
        without copying an entire environment or its immutable geometry.
        """

        return {
            "placements": list(self.placements),
            "placement_by_id": dict(self.placement_by_id),
            "adjacency_map": {
                identifier: set(neighbors)
                for identifier, neighbors in self.adjacency_map.items()
            },
            "occupied": dict(self.occupied),
            "module_uses": dict(self.module_uses),
            "spatial_buckets": {
                bucket: set(identifiers)
                for bucket, identifiers in self.spatial_buckets.items()
            },
            "placement_bounds": dict(self.placement_bounds),
            "core_ids": set(self.core_ids),
            "attachment_edges": {
                edge_id: dict(edge) for edge_id, edge in self.attachment_edges.items()
            },
            "attachment_by_angle": {
                angle: set(edge_ids)
                for angle, edge_ids in self.attachment_by_angle.items()
            },
            "attachment_by_placement": {
                identifier: set(edge_ids)
                for identifier, edge_ids in self.attachment_by_placement.items()
            },
            "attachment_order": deque(self.attachment_order),
            "next_attachment_id": self.next_attachment_id,
            "filled_area": self.filled_area,
            "rentable_area": self.rentable_area,
            "repeated_uses": self.repeated_uses,
            "done": self.done,
            "consecutive_proposal_failures": self.consecutive_proposal_failures,
            "attachment_query_cursor": self.attachment_query_cursor,
        }

    def _restore_stack_commit_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        """Restore the exact placement-owned state captured above."""

        self.placements = checkpoint["placements"]
        self.placement_by_id = checkpoint["placement_by_id"]
        self.adjacency_map = checkpoint["adjacency_map"]
        self.occupied = checkpoint["occupied"]
        self.module_uses = checkpoint["module_uses"]
        self.spatial_buckets = checkpoint["spatial_buckets"]
        self.placement_bounds = checkpoint["placement_bounds"]
        self.core_ids = checkpoint["core_ids"]
        self.attachment_edges = checkpoint["attachment_edges"]
        self.attachment_by_angle = checkpoint["attachment_by_angle"]
        self.attachment_by_placement = checkpoint["attachment_by_placement"]
        self.attachment_order = checkpoint["attachment_order"]
        self.next_attachment_id = checkpoint["next_attachment_id"]
        self.filled_area = checkpoint["filled_area"]
        self.rentable_area = checkpoint["rentable_area"]
        self.repeated_uses = checkpoint["repeated_uses"]
        self.done = checkpoint["done"]
        self.consecutive_proposal_failures = checkpoint[
            "consecutive_proposal_failures"
        ]
        self.attachment_query_cursor = checkpoint["attachment_query_cursor"]

    def place(
        self,
        candidate: PlacementCandidate,
        *,
        core_stack_id: str | None = None,
        core_stack_trigger_floor: int | None = None,
    ) -> dict:
        """Commit one candidate and return its world-space protocol record."""

        if core_stack_id is not None and candidate.module.get("category") != "core":
            raise CoreStackingError("only core placements may be locked into a core stack")
        if candidate.poly and not candidate.cells:
            candidate.cells = G.rasterize_polygon(candidate.poly)
        identifier = f"f{self.index}:p{len(self.placements)}"
        center = G.polygon_centroid(candidate.poly)
        placement = {
            "id": identifier,
            "moduleId": candidate.module["id"],
            "category": candidate.module["category"],
            "family": candidate.module.get("family", "procedural"),
            "poly": candidate.poly,
            "cells": candidate.cells,
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
        if core_stack_id is not None:
            placement.update(
                {
                    "coreStackId": core_stack_id,
                    "coreStackLocked": True,
                    "coreStackTriggerFloor": core_stack_trigger_floor,
                    "localAnchor": {
                        "x": float(candidate.anchor_x),
                        "y": float(candidate.anchor_y),
                    },
                }
            )
        self.placements.append(placement)
        self.placement_by_id[identifier] = placement
        self.adjacency_map[identifier] = set(candidate.neighbors)
        for neighbor in candidate.neighbors:
            self.adjacency_map.setdefault(neighbor, set()).add(identifier)
        for cell in candidate.cells:
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
        self.consecutive_proposal_failures = 0

        dx, dy = self.offset
        world_center = {"x": center["x"] + dx, "y": center["y"] + dy}
        public_record = {
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
        if core_stack_id is not None:
            stack_fields = {
                "coreStackId": core_stack_id,
                "coreStackLocked": True,
                "coreStackTriggerFloor": core_stack_trigger_floor,
                "localAnchor": {
                    "x": float(candidate.anchor_x),
                    "y": float(candidate.anchor_y),
                },
            }
            public_record.update(stack_fields)
            public_record["module"].update(stack_fields)
        return public_record

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
            "proposalFailures": self.consecutive_proposal_failures,
        }

    def validate_topology(self, single_floor: bool, core_spacing: float) -> tuple[bool, list[str]]:
        """Validate terminal graph constraints with shortest room-cost paths."""

        violations: list[str] = []
        if not self.placements:
            return False, ["emptyLayout"]

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
                if math.isinf(dist):
                    violations.append("noPathToCore")
                elif dist > 30.0:
                    violations.append("travelLimitCap")
        return not violations, sorted(set(violations))

    def _deep_interior_room_metrics(self) -> tuple[int, float, float, float]:
        """Compute count, area, ratio, and un-diluted depth penalty score of habitable rooms based on hop distance from facade."""
        habitable_rooms = [p for p in self.placements if p.get("category") in ("room", "special")]
        if not habitable_rooms:
            return 0, 0.0, 0.0, 0.0
            
        polys = [p["poly"] for p in self.placements]
        segs = G.exposed_wall_segments(polys)
        
        # A room is a Facade Room (Depth 0) if it has exposed exterior wall segments or touches site boundary
        facade_room_ids = set()
        for p in habitable_rooms:
            if float(p.get("outerExposure", 0.0)) >= 0.5:
                facade_room_ids.add(p["id"])
                
        for seg in segs:
            if float(seg.get("length", 0.0)) >= 0.4:
                poly_idx = seg.get("polygonIndex")
                if poly_idx is not None and poly_idx < len(self.placements):
                    p = self.placements[poly_idx]
                    if p.get("category") in ("room", "special"):
                        facade_room_ids.add(p["id"])
                        
        if not facade_room_ids:
            total_area = sum(float(p.get("area", 0.0)) for p in habitable_rooms)
            # All rooms are completely buried with no facade contact: assign max penalty to all
            depth_score = sum(45.0 * max(0.5, float(p.get("area", 15.0)) / 15.0) for p in habitable_rooms)
            return len(habitable_rooms), total_area, 1.0, depth_score

        depth: dict[str, int] = {rid: 0 for rid in facade_room_ids}
        queue = list(facade_room_ids)
        while queue:
            curr_id = queue.pop(0)
            curr_depth = depth[curr_id]
            for neighbor_id in self.adjacency_map.get(curr_id, ()):
                if neighbor_id in self.placement_by_id:
                    neighbor = self.placement_by_id[neighbor_id]
                    if neighbor.get("category") in ("room", "special") and neighbor_id not in depth:
                        depth[neighbor_id] = curr_depth + 1
                        queue.append(neighbor_id)
                        
        deep_rooms = [p for p in habitable_rooms if depth.get(p["id"], 999) >= 2]
        deep_count = len(deep_rooms)
        deep_area = sum(float(p.get("area", 0.0)) for p in deep_rooms)
        total_rentable = sum(float(p.get("area", 0.0)) for p in habitable_rooms)
        deep_ratio = _safe_ratio(deep_area, total_rentable)
        
        # Direct per-room progressive depth penalty:
        # d=0 -> 0.0 (facade room, direct daylight)
        # d=1 -> 1.5 (mild penalty for borrowed daylight)
        # d=2 -> 8.0 (windowless room, clear defect)
        # d=3 -> 18.0 (severely buried room)
        # d=4 -> 30.0 (deep tomb)
        # d>=5 -> 45.0 + 10.0*(d-5) (catastrophic interior void)
        depth_penalty_score = 0.0
        for p in habitable_rooms:
            d = depth.get(p["id"], 999)
            if d == 1:
                base_rate = 1.5
            elif d == 2:
                base_rate = 8.0
            elif d == 3:
                base_rate = 18.0
            elif d == 4:
                base_rate = 30.0
            elif d >= 5:
                base_rate = 45.0 + 10.0 * min(d - 5, 5)
            else:
                base_rate = 0.0
                
            if base_rate > 0.0:
                area_factor = max(0.5, float(p.get("area", 15.0)) / 15.0)
                depth_penalty_score += base_rate * area_factor
                
        return deep_count, deep_area, deep_ratio, depth_penalty_score

    def _narrow_facade_chasm_metrics(self, exposed_segments: Sequence[dict], exposed_perimeter: float) -> tuple[float, float]:
        """Cast outward normal ray from each exposed facade wall midpoint and multiply by edge length."""
        if not exposed_segments or exposed_perimeter <= 1e-4:
            return 0.0, 0.0
            
        occluded_length = 0.0
        for i, seg in enumerate(exposed_segments):
            length = float(seg["length"])
            if length < 0.8:
                continue
            p1 = seg["a"]
            p2 = seg["b"]
            dx = float(p2["x"]) - float(p1["x"])
            dy = float(p2["y"]) - float(p1["y"])
            if length <= 1e-4:
                continue
            ux = dx / length
            uy = dy / length
            
            # Outward normal
            nx = uy
            ny = -ux
            
            mid = {
                "x": 0.5 * (float(p1["x"]) + float(p2["x"])),
                "y": 0.5 * (float(p1["y"]) + float(p2["y"]))
            }
            
            other_segs = [s for j, s in enumerate(exposed_segments) if j != i]
            t = G.ray_intersect_segments(mid, (nx, ny), other_segs, min_dist=0.05, max_dist=3.0)
            if t is not None and t < 3.0:
                severity = (3.0 - t) / 3.0
                occluded_length += length * severity
                
        chasm_ratio = _safe_ratio(occluded_length, exposed_perimeter)
        return occluded_length, chasm_ratio

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

        deep_count, deep_area, deep_ratio, depth_penalty_score = self._deep_interior_room_metrics()
        chasm_occluded_len, chasm_ratio = self._narrow_facade_chasm_metrics(segments, exposed_perimeter)

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
            "deepRoomCount": deep_count,
            "deepRoomArea": deep_area,
            "deepRoomRatio": deep_ratio,
            "depthPenaltyScore": depth_penalty_score,
            "facadeChasmOccludedLength": chasm_occluded_len,
            "facadeChasmRatio": chasm_ratio,
        }


class StepProfiler:
    """Lightweight per-episode timing profiler for step and evaluation phases."""
    
    def __init__(self) -> None:
        self.reset()
    
    def reset(self) -> None:
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
        _configure_torch_runtime(self.device)
        self.model = PolicyModel().to(self.device)
        self.optimizer = optim.Adam(self.model.parameters(), lr=float(self.settings["learningRate"]))
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)
        self.mode: str = "training"
        self.generation_id = 0
        self.episode = 0
        self.step_number = 0
        self.step_profiler = StepProfiler()
        self.environments: list[FloorEnvironment] = []
        self.dictionary: list[dict] = []
        self.shape_log_probs: list[torch.Tensor] = []
        self.building_shape_log_probs: list[torch.Tensor] = []
        self.placement_log_probs: list[torch.Tensor] = []
        self.core_stack_records: list[dict[str, Any]] = []
        self.core_stacking_metadata: dict[str, Any] = {
            "enabled": False,
            "status": "unprepared",
            "mode": "disabled",
            "boundaryPolicy": "unchanged",
            "siteResampleAttempts": 0,
            "initialCandidateCount": 0,
        }
        self._prepared_initial_core_stacks: list[CoreStackCandidate] = []
        self.placement_log_probs_by_environment: dict[int, list[torch.Tensor]] = {}
        self.placement_decisions: list[PlacementPolicyDecision] = []
        self.baseline = 0.35
        self.score_history: list[float] = []
        self.best_score = 0.0
        self.topology_multiplier = 0.05
        self.last_loss = 0.0
        self.last_actor_loss = 0.0
        self.last_value_loss = 0.0
        self.last_entropy = 0.0
        self.last_gradient_norm = 0.0
        self.last_advantage = 0.0
        self.generation_time_history: deque[float] = deque(maxlen=RELATIVE_TIME_WINDOW)
        self.frontier_growth_history: deque[float] = deque(maxlen=RELATIVE_TIME_WINDOW)
        self.generation_time_baseline: float | None = None
        self.frontier_growth_baseline: float | None = None
        self.baseline_transition_remaining = 0
        self.baseline_transition_anchor_reward = 0.0
        self.reward_settings_signature = (self._reward_signature(self.settings), None, None)
        self.last_frontier_reward = 0.0
        self.diversity_archive: deque[tuple[list[float], float]] = deque(maxlen=8)
        self.last_dpp_diversity = 0.0
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
            int(settings["dictCap"]),
            float(settings["angleStep"]),
            float(settings["coreSpacing"]),
            int(settings["travelLimit"]),
            int(settings["seed"]),
        )

    def _checkpoint_reward_state(self) -> dict[str, Any]:
        return {
            "generationTimeHistory": list(self.generation_time_history),
            "frontierGrowthHistory": list(self.frontier_growth_history),
            "generationTimeBaseline": self.generation_time_baseline,
            "frontierGrowthBaseline": self.frontier_growth_baseline,
            "baselineTransitionRemaining": self.baseline_transition_remaining,
            "baselineTransitionAnchorReward": self.baseline_transition_anchor_reward,
            "lastFrontierReward": self.last_frontier_reward,
            "settingsSignature": self.reward_settings_signature,
        }

    def _restore_checkpoint_reward_state(self, state: Any) -> None:
        """Restore bounded reward references, or reset absent legacy state."""

        if state is None:
            self.generation_time_history = deque(maxlen=RELATIVE_TIME_WINDOW)
            self.frontier_growth_history = deque(maxlen=RELATIVE_TIME_WINDOW)
            self.generation_time_baseline = None
            self.frontier_growth_baseline = None
            self.baseline_transition_remaining = 0
            self.baseline_transition_anchor_reward = 0.0
            self.last_frontier_reward = 0.0
            self.reward_settings_signature = (self._reward_signature(self.settings), None, None)
            return
        if not isinstance(state, dict):
            raise ValueError("checkpoint reward state is invalid")

        def finite_history(key: str) -> deque[float]:
            raw = state.get(key, [])
            if not isinstance(raw, (list, tuple)) or len(raw) > RELATIVE_TIME_WINDOW:
                raise ValueError(f"checkpoint {key} is invalid")
            values = [float(value) for value in raw]
            if not all(math.isfinite(value) for value in values):
                raise ValueError(f"checkpoint {key} is not finite")
            return deque(values, maxlen=RELATIVE_TIME_WINDOW)

        def optional_finite(key: str) -> float | None:
            raw = state.get(key)
            if raw is None:
                return None
            value = float(raw)
            if not math.isfinite(value):
                raise ValueError(f"checkpoint {key} is not finite")
            return value

        self.generation_time_history = finite_history("generationTimeHistory")
        self.frontier_growth_history = finite_history("frontierGrowthHistory")
        self.generation_time_baseline = optional_finite("generationTimeBaseline")
        self.frontier_growth_baseline = optional_finite("frontierGrowthBaseline")
        transition = int(state.get("baselineTransitionRemaining", 0))
        if not 0 <= transition <= BASELINE_TRANSITION_EPISODES:
            raise ValueError("checkpoint baseline transition is invalid")
        self.baseline_transition_remaining = transition
        self.baseline_transition_anchor_reward = float(
            optional_finite("baselineTransitionAnchorReward") or 0.0
        )
        self.last_frontier_reward = float(optional_finite("lastFrontierReward") or 0.0)

        def freeze(value: Any) -> Any:
            if isinstance(value, (list, tuple)):
                return tuple(freeze(item) for item in value)
            return value

        signature = freeze(state.get("settingsSignature"))
        if not isinstance(signature, tuple) or len(signature) != 3:
            raise ValueError("checkpoint reward settings signature is invalid")
        self.reward_settings_signature = signature

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

    def _relative_frontier_reward(
        self,
        *,
        update_state: bool = True,
    ) -> dict[str, float | int]:
        """Reward deterministic frontier growth; wall time remains telemetry."""

        if not update_state:
            snapshot = (
                deque(self.generation_time_history, maxlen=self.generation_time_history.maxlen),
                deque(self.frontier_growth_history, maxlen=self.frontier_growth_history.maxlen),
                self.generation_time_baseline,
                self.frontier_growth_baseline,
                self.baseline_transition_remaining,
                self.last_frontier_reward,
            )
            try:
                return self._relative_frontier_reward(update_state=True)
            finally:
                (
                    self.generation_time_history,
                    self.frontier_growth_history,
                    self.generation_time_baseline,
                    self.frontier_growth_baseline,
                    self.baseline_transition_remaining,
                    self.last_frontier_reward,
                ) = snapshot

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
            MAX_FRONTIER_REWARD * frontier_relative - exploit_penalty,
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
        policy = settings.get("atriumPolicy", "none")
        none_choice = next((item for item in candidates if item["id"] == "none"), candidates[0])
        nonempty = [item for item in candidates if item.get("holes")]
        if policy == "central" and nonempty:
            return min(
                nonempty,
                key=lambda item: (self._central_atrium_distance(boundary, item), str(item["id"])),
            ), None
        return none_choice, None

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
        attempt: int = 0,
    ) -> tuple[list[FloorEnvironment], list[torch.Tensor]]:
        records: list[tuple[dict, dict, dict, G.RNG]] = []
        atrium_log_probs: list[torch.Tensor] = []
        # A failed common-core preflight rejects this entire group of floors.
        # The next attempt changes every floor seed together; individual floors
        # are never silently replaced or relaxed to rectangular boundaries.
        base_seed = int(settings["seed"]) + generation_id * 104729 + attempt * 1_000_003
        master_rng = G.RNG(base_seed)
        floor_count = int(settings["parallelEnvironments"])
        tier = settings.get("siteAreaTier", "ANY")
        floor_target_areas = G.sample_building_floor_areas(tier, floor_count, master_rng)

        for index in range(floor_count):
            rng = G.RNG(base_seed + index * 8191)
            floor_settings = dict(settings)
            floor_settings["targetSiteArea"] = floor_target_areas[index]
            boundary = G.make_boundary(settings["boundaryType"], rng.fork(11), floor_settings)
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
        """Seed multi-floor episodes with one learned, stackable core module."""

        if bool(settings["singleFloor"]) or len(environments) <= 1:
            return [], []
        module, log_prob = self._sample_custom_shape(
            settings, environments, slot_index=0, force_core=True
        )
        return [module], [log_prob]

    def _sample_custom_shape(
        self,
        settings: dict[str, Any],
        environments: Sequence[FloorEnvironment],
        slot_index: int,
        *,
        force_core: bool = False,
    ) -> tuple[dict, torch.Tensor]:
        """Propose and synthesize one custom shape dynamically."""
        floor_tensor = torch.tensor(
            self._site_descriptor(environments, settings), dtype=torch.float32, device=self.device
        )
        pooled_site = self.model.encode_sites(floor_tensor)
        epsilon = max(0.18, 0.65 * math.exp(-self.episode / 50.0))
        category = "shape"
        
        parameter_logits = tuple(
            torch.nan_to_num(logits, nan=0.0, posinf=20.0, neginf=-20.0).clamp(-30.0, 30.0)
            for logits in self.model.shape_parameter_logits(pooled_site)
        )
        
        num_edges_logits = parameter_logits[0] / max(0.32, 0.90 * math.exp(-self.episode / 45.0))
        is_step0 = force_core or (any(not env.placements for env in environments) and not bool(settings.get("singleFloor"))) or (slot_index == 0 and not bool(settings.get("singleFloor")))
        triangle_feasible = (
            float(settings.get("maxEdge", 9.0)) ** 2 * math.sqrt(3.0) * 0.25 + 1.0e-8 >= 24.0
        )
        max_edges = int(settings.get("maxEdges", 8))
        if max_edges <= 3:
            edge_count_mask = torch.tensor([1.0, 0.0], device=self.device)
        elif is_step0 and not triangle_feasible:
            edge_count_mask = torch.tensor([0.0, 1.0], device=self.device)
        else:
            edge_count_mask = torch.tensor([1.0, 1.0], device=self.device)
        masked_num_edges_logits = torch.where(
            edge_count_mask > 0,
            num_edges_logits,
            torch.tensor(-1.0e9, device=self.device),
        )
        num_edges_probs = torch.softmax(masked_num_edges_logits, dim=0)
        num_edges_behavior = (
            (1.0 - epsilon) * num_edges_probs
            + epsilon * (edge_count_mask / edge_count_mask.sum())
        )
        num_edges_dist = torch.distributions.Categorical(probs=num_edges_behavior)

        min_edge = float(settings.get("minEdge", 1.0))
        max_edge = float(settings.get("maxEdge", 9.0))

        if is_step0:
            step0_min = max(min_edge, min(4.5, max_edge))
            edge_valid_mask = torch.tensor(
                [1.0 if (step0_min - 1e-4 <= length <= max_edge + 1e-4) else 0.0 for length in G.EDGE_PALETTE],
                device=self.device,
            )
            if edge_valid_mask.sum() == 0:
                edge_valid_mask = torch.tensor(
                    [1.0 if (min_edge - 1e-4 <= length <= max_edge + 1e-4) else 0.0 for length in G.EDGE_PALETTE],
                    device=self.device,
                )
        else:
            edge_valid_mask = torch.tensor(
                [1.0 if (min_edge - 1e-4 <= length <= max_edge + 1e-4) else 0.0 for length in G.EDGE_PALETTE],
                device=self.device,
            )
        if edge_valid_mask.sum() == 0:
            edge_valid_mask[0] = 1.0

        module = None
        total_log_prob = torch.tensor(0.0, device=self.device)
        k = 4 if max_edges >= 4 else 3

        for attempt in range(8):
            # Resample k on each attempt
            num_edges_action = num_edges_dist.sample()
            k = int(num_edges_action.item()) + 3  # 3 (triangle) or 4 (quad)
            num_edges_log_prob = torch.log_softmax(num_edges_logits, dim=0)[num_edges_action]
            trace_log_probs = [num_edges_log_prob]

            edge_length_logits = parameter_logits[1:k]
            edge_length_indices = []
            for logit in edge_length_logits:
                masked_logits = torch.where(edge_valid_mask > 0, logit, torch.tensor(-1.0e9, device=self.device))
                probs = torch.softmax(masked_logits, dim=0)
                behavior_probs = (1.0 - epsilon) * probs + epsilon * (edge_valid_mask / edge_valid_mask.sum())
                dist = torch.distributions.Categorical(probs=behavior_probs)
                action = dist.sample()
                edge_length_indices.append(int(action.item()))
                trace_log_probs.append(dist.log_prob(action))

            angle_logits = parameter_logits[4 : 4 + (k - 2)]
            angle_indices = []
            for logit in angle_logits:
                probs = torch.softmax(logit, dim=0)
                behavior_probs = (1.0 - epsilon) * probs + epsilon * torch.full_like(probs, 1.0 / len(G.ANGLE_PALETTE))
                dist = torch.distributions.Categorical(probs=behavior_probs)
                action = dist.sample()
                angle_indices.append(int(action.item()))
                trace_log_probs.append(dist.log_prob(action))

            try:
                candidate_module = G.synthesize_custom_module(
                    settings,
                    category,
                    k,
                    edge_length_indices,
                    angle_indices,
                    f"s{slot_index}",
                )
                if is_step0 and float(candidate_module["area"]) + 1.0e-8 < 24.0:
                    continue

                module = candidate_module
                total_log_prob = torch.stack(trace_log_probs).sum()
                break
            except ValueError:
                continue

        if module is None or (is_step0 and float(module["area"]) + 1.0e-8 < 24.0):
            large_edge_indices = [i for i, l in enumerate(G.EDGE_PALETTE) if min_edge - 1e-4 <= l <= max_edge + 1e-4]
            if not large_edge_indices:
                large_edge_indices = [0]
            e0 = large_edge_indices[-1] if is_step0 else large_edge_indices[0]
            fallback_k = 3 if max_edges <= 3 else k
            fallback_angle = 60.0 if fallback_k == 3 else 90.0
            ang0 = G.ANGLE_PALETTE.index(fallback_angle) if fallback_angle in G.ANGLE_PALETTE else 0
            try:
                module = G.synthesize_custom_module(
                    settings,
                    category,
                    fallback_k,
                    [e0] * (fallback_k - 1),
                    [ang0] * (fallback_k - 2),
                    f"s{slot_index}",
                )
            except Exception:
                if fallback_k == 3:
                    poly = [
                        {"x": 0.0, "y": 0.0},
                        {"x": min_edge, "y": 0.0},
                        {"x": min_edge * 0.5, "y": min_edge * math.sqrt(3.0) * 0.5},
                    ]
                else:
                    poly = [
                        {"x": 0.0, "y": 0.0},
                        {"x": min_edge, "y": 0.0},
                        {"x": min_edge, "y": min_edge},
                        {"x": 0.0, "y": min_edge},
                    ]
                module = G._module_record(
                    identifier=f"s{slot_index}",
                    name=f"Custom {fallback_k}-Edge Fallback",
                    category=category,
                    poly=poly,
                    family="custom-policy",
                    edge_range_compatible=True,
                    source_parameters={"generator": "custom-fallback", "numEdges": fallback_k},
                )
            total_log_prob = torch.stack(trace_log_probs).sum()

        if is_step0 and float(module["area"]) + 1.0e-8 < 24.0:
            maximum_edge = float(settings.get("maxEdge", 9.0))
            if max_edges <= 3 or k == 3:
                height = maximum_edge * math.sqrt(3.0) * 0.5
                poly = [
                    {"x": 0.0, "y": 0.0},
                    {"x": maximum_edge, "y": 0.0},
                    {"x": maximum_edge * 0.5, "y": height},
                ]
            else:
                minimum_edge = float(settings.get("minEdge", 3.0))
                height = max(minimum_edge, 24.0 / maximum_edge)
                poly = [
                    {"x": 0.0, "y": 0.0},
                    {"x": maximum_edge, "y": 0.0},
                    {"x": maximum_edge, "y": height},
                    {"x": 0.0, "y": height},
                ]
            module = G._module_record(
                identifier=f"s{slot_index}",
                name="Guaranteed Core Proposal",
                category=category,
                poly=poly,
                family="custom-policy",
                edge_range_compatible=True,
                source_parameters={"generator": "guaranteed-core-fallback", "numEdges": 3 if (max_edges <= 3 or k == 3) else 4},
            )
            
        if force_core:
            module = {
                **module,
                "category": "core",
                "name": f"Stacked Core {slot_index + 1}",
            }
        canonical = self._canonical_module(
            module, float(settings["angleStep"]), phase=self.episode + slot_index
        )
        return canonical, total_log_prob

    def _frontier_compatible_modules(
        self,
        settings: dict[str, Any],
        environment: FloorEnvironment,
        slot_index: int,
    ) -> list[dict]:
        """Build bounded room proposals that exactly match exposed wall ports.

        Learned free-form proposals remain the primary path. These rectangles
        are a feasibility repair for large valid cores whose discrete edge
        lengths otherwise make every later random room impossible to attach.
        """

        minimum = float(settings["minEdge"])
        maximum = float(settings["maxEdge"])
        edges = sorted(
            environment.attachment_edges.values(),
            key=lambda edge: (not bool(edge.get("preferred")), -int(edge["id"])),
        )
        dimensions: list[tuple[float, float, float]] = []
        seen: set[tuple[float, float]] = set()
        for edge in edges:
            source_length = float(edge["length"])
            for connection_length in (
                source_length,
                source_length * 0.5,
                source_length * 2.0,
            ):
                if not minimum - 1.0e-8 <= connection_length <= maximum + 1.0e-8:
                    continue
                depth = _clamp(
                    max(minimum, 8.0 / max(connection_length, 1.0e-8)),
                    minimum,
                    maximum,
                )
                signature = (round(connection_length, 6), round(depth, 6))
                if signature in seen:
                    continue
                seen.add(signature)
                dimensions.append((connection_length, depth, source_length))
                if len(dimensions) >= 8:
                    break
            if len(dimensions) >= 8:
                break

        modules = []
        for variant, (width, depth, source_length) in enumerate(dimensions):
            poly = [
                {"x": 0.0, "y": 0.0},
                {"x": width, "y": 0.0},
                {"x": width, "y": depth},
                {"x": 0.0, "y": depth},
            ]
            module = G._module_record(
                identifier=f"s{slot_index}",
                name=f"Frontier-Compatible Room {variant + 1}",
                category="shape",
                poly=poly,
                family="frontier-compatible",
                edge_range_compatible=True,
                source_parameters={
                    "generator": "frontier-compatible",
                    "sourceEdgeLength": source_length,
                    "connectionLength": width,
                    "depth": depth,
                },
            )
            modules.append(
                self._canonical_module(
                    module,
                    float(settings["angleStep"]),
                    phase=self.episode + slot_index + variant,
                )
            )
        return modules

    @staticmethod
    def _core_transform_signature(
        module: dict,
        rotation: dict,
        anchor_x: float,
        anchor_y: float,
    ) -> tuple[str, float, float, float]:
        return (
            str(module["id"]),
            round(float(rotation.get("angle", 0.0)), 6),
            round(float(anchor_x), 6),
            round(float(anchor_y), 6),
        )

    def _core_stack_at_transform(
        self,
        environments: Sequence[FloorEnvironment],
        module: dict,
        rotation: dict,
        anchor_x: float,
        anchor_y: float,
        settings: dict[str, Any],
        orientation_basis: float,
    ) -> CoreStackCandidate | None:
        """Prevalidate one exact local transform on every floor."""

        floor_candidates: list[PlacementCandidate] = []
        for environment in environments:
            if environment.done or len(environment.placements) >= int(settings["maxModules"]):
                return None
            room_core_costs = (
                environment._room_crossing_costs_to_core()
                if environment.core_ids
                else {}
            )
            candidate = environment._candidate_from_anchor(
                module,
                rotation,
                anchor_x,
                anchor_y,
                settings,
                orientation_basis,
                room_core_costs,
                placement_category="core",
            )
            if candidate is None or not environment._materialize_candidate(
                candidate, settings, orientation_basis
            ):
                return None
            if len(candidate.features) == PLACEMENT_FEATURE_DIM - 2:
                candidate.features.extend((0.0, 0.0))
            if len(candidate.features) != PLACEMENT_FEATURE_DIM:
                raise CoreStackingError("invalid feature width in shared core candidate")
            floor_candidates.append(candidate)
        if len(floor_candidates) != len(environments):
            return None
        return CoreStackCandidate(
            module=module,
            rotation=rotation,
            anchor_x=float(anchor_x),
            anchor_y=float(anchor_y),
            floor_candidates=floor_candidates,
        )

    def _initial_core_proposals(
        self,
        environments: Sequence[FloorEnvironment],
        dictionary: Sequence[dict],
    ) -> list[tuple[dict, dict, float, float]]:
        """Propose transforms from cells shared by all original floor sites."""

        if not environments:
            return []
        common_keys = set(environments[0].site["cellSet"])
        for environment in environments[1:]:
            common_keys.intersection_update(environment.site["cellSet"])
        if not common_keys:
            return []

        def target_score(cell_key: str) -> tuple[float, int, int]:
            x_text, y_text = cell_key.split(",")
            x, y = int(x_text), int(y_text)
            clearance = min(
                float(environment.site.get("distance", {}).get(cell_key, 0.0))
                for environment in environments
            )
            return (-clearance, x, y)

        targets = []
        for cell_key in heapq.nsmallest(16, common_keys, key=target_score):
            x_text, y_text = cell_key.split(",")
            targets.append({"x": int(x_text), "y": int(y_text)})

        proposals: list[tuple[dict, dict, float, float]] = []
        seen: set[tuple[str, float, float, float]] = set()
        for target in targets:
            for module in dictionary:
                for rotation in module.get("rotations", ()):
                    for cell in rotation.get("cells", ())[:4]:
                        anchor_x = float(target["x"] - cell["x"])
                        anchor_y = float(target["y"] - cell["y"])
                        signature = self._core_transform_signature(
                            module, rotation, anchor_x, anchor_y
                        )
                        if signature in seen:
                            continue
                        seen.add(signature)
                        proposals.append((module, rotation, anchor_x, anchor_y))
                        if len(proposals) >= CORE_STACK_PROPOSAL_LIMIT:
                            return proposals
        return proposals

    def _shared_core_stack_candidates(
        self,
        orientation_basis: float,
        *,
        environments: Sequence[FloorEnvironment] | None = None,
        dictionary: Sequence[dict] | None = None,
        settings: dict[str, Any] | None = None,
    ) -> list[CoreStackCandidate]:
        """Return exact shared transforms; a core is never a floor-local action."""

        active_settings = settings or self.settings
        floors = list(self.environments if environments is None else environments)
        modules = list(self.dictionary if dictionary is None else dictionary)
        if bool(active_settings["singleFloor"]) or len(floors) <= 1 or not modules:
            return []
        if any(
            environment.done
            or len(environment.placements) >= int(active_settings["maxModules"])
            for environment in floors
        ):
            return []

        placing_first = all(not environment.placements for environment in floors)
        primary_site_area = float(floors[0].site["exactArea"]) if floors else 1000.0
        max_cores = _max_cores_for_site(primary_site_area)
        if not placing_first:
            # Multi-floor cores scale with building area. Offer subsequent
            # cores after every floor has developed sufficient rooms, matching the quality
            # gate used by the independent-floor policy.
            core_counts = [
                sum(
                    1
                    for placement in environment.placements
                    if placement.get("category") == "core"
                )
                for environment in floors
            ]
            room_counts = [
                sum(
                    1
                    for placement in environment.placements
                    if placement.get("category") == "room"
                )
                for environment in floors
            ]
            if any(count == 0 or count >= max_cores for count in core_counts):
                return []
            min_current_cores = min(core_counts)
            if any(count < SECOND_CORE_MIN_ROOMS * min_current_cores for count in room_counts):
                return []
        proposal_by_signature: dict[
            tuple[str, float, float, float], tuple[dict, dict, float, float]
        ] = {}
        if placing_first:
            proposals = self._initial_core_proposals(floors, modules)
            for module, rotation, anchor_x, anchor_y in proposals:
                signature = self._core_transform_signature(
                    module, rotation, anchor_x, anchor_y
                )
                proposal_by_signature[signature] = (
                    module,
                    rotation,
                    anchor_x,
                    anchor_y,
                )
        else:
            # Existing layouts use their bounded exposed-edge frontiers as the
            # proposal source. Every proposal is still rechecked on every floor.
            for module in modules:
                for environment in floors:
                    for candidate in environment.generate_candidates_for_module(
                        module,
                        active_settings,
                        orientation_basis,
                        category_filter=("core",),
                    ):
                        if candidate.module.get("category") != "core":
                            continue
                        signature = self._core_transform_signature(
                            module,
                            candidate.rotation,
                            candidate.anchor_x,
                            candidate.anchor_y,
                        )
                        proposal_by_signature.setdefault(
                            signature,
                            (
                                module,
                                candidate.rotation,
                                candidate.anchor_x,
                                candidate.anchor_y,
                            ),
                        )
                        if len(proposal_by_signature) >= CORE_STACK_PROPOSAL_LIMIT:
                            break
                    if len(proposal_by_signature) >= CORE_STACK_PROPOSAL_LIMIT:
                        break
                if len(proposal_by_signature) >= CORE_STACK_PROPOSAL_LIMIT:
                    break

            if len(proposal_by_signature) < CORE_STACK_PROPOSAL_LIMIT:
                common_unoccupied = set(floors[0].site["cellSet"]) - set(floors[0].occupied)
                for env in floors[1:]:
                    common_unoccupied.intersection_update(set(env.site["cellSet"]) - set(env.occupied))

                core_centers = []
                for env in floors:
                    for p in env.placements:
                        if p.get("category") == "core":
                            core_centers.append(p["center"])

                valid_remote_cells = []
                core_spacing = float(active_settings.get("coreSpacing", 8.0))
                for cell_key in common_unoccupied:
                    x_t, y_t = cell_key.split(",")
                    cx, cy = float(x_t) + 0.5, float(y_t) + 0.5
                    if all(math.hypot(cx - cc["x"], cy - cc["y"]) >= core_spacing for cc in core_centers):
                        clearance = min(float(env.site.get("distance", {}).get(cell_key, 0.0)) for env in floors)
                        valid_remote_cells.append((clearance, int(x_t), int(y_t)))

                valid_remote_cells.sort(key=lambda t: -t[0])
                for _, rx, ry in valid_remote_cells[:12]:
                    for module in modules:
                        for rotation in module.get("rotations", ()):
                            for cell in rotation.get("cells", ())[:4]:
                                anchor_x = float(rx - cell["x"])
                                anchor_y = float(ry - cell["y"])
                                signature = self._core_transform_signature(
                                    module, rotation, anchor_x, anchor_y
                                )
                                if signature in proposal_by_signature:
                                    continue
                                proposal_by_signature[signature] = (
                                    module,
                                    rotation,
                                    anchor_x,
                                    anchor_y,
                                )
                                if len(proposal_by_signature) >= CORE_STACK_PROPOSAL_LIMIT:
                                    break
                            if len(proposal_by_signature) >= CORE_STACK_PROPOSAL_LIMIT:
                                break
                        if len(proposal_by_signature) >= CORE_STACK_PROPOSAL_LIMIT:
                            break

        shared: list[CoreStackCandidate] = []
        for signature in sorted(proposal_by_signature):
            module, rotation, anchor_x, anchor_y = proposal_by_signature[signature]
            candidate = self._core_stack_at_transform(
                floors,
                module,
                rotation,
                anchor_x,
                anchor_y,
                active_settings,
                orientation_basis,
            )
            if candidate is not None:
                shared.append(candidate)
                if len(shared) >= CORE_STACK_CANDIDATE_LIMIT:
                    break
        return shared

    def _commit_core_stack(
        self,
        candidate: CoreStackCandidate,
        log_prob: torch.Tensor,
        orientation_basis: float,
        *,
        decision_features: Sequence[Sequence[float]] | None = None,
        decision_action_index: int = 0,
        decision_temperature: float = 1.0,
    ) -> list[dict]:
        """Revalidate and atomically commit one building-level core action."""

        revalidated = self._core_stack_at_transform(
            self.environments,
            candidate.module,
            candidate.rotation,
            candidate.anchor_x,
            candidate.anchor_y,
            self.settings,
            orientation_basis,
        )
        if revalidated is None:
            raise CoreStackingError("selected core stack became invalid before commit")

        stack_id = (
            f"g{self.generation_id}:e{self.episode}:"
            f"core{len(self.core_stack_records)}"
        )
        checkpoints = [
            environment._stack_commit_checkpoint()
            for environment in self.environments
        ]
        placements: list[dict] = []
        try:
            for environment, floor_candidate in zip(
                self.environments, revalidated.floor_candidates
            ):
                placements.append(
                    environment.place(
                        floor_candidate,
                        core_stack_id=stack_id,
                        core_stack_trigger_floor=None,
                    )
                )
        except Exception as error:
            for environment, checkpoint in zip(self.environments, checkpoints):
                environment._restore_stack_commit_checkpoint(checkpoint)
            raise CoreStackingError(
                f"core stack {stack_id} rolled back after commit failure"
            ) from error

        # One building action contributes exactly one detached/recomputed
        # policy decision, independent of floor count.
        if decision_features is None:
            self._record_placement_log_prob(
                BUILDING_TRAJECTORY_INDEX, log_prob.detach().cpu()
            )
        else:
            self._record_placement_decision(
                BUILDING_TRAJECTORY_INDEX,
                decision_features,
                decision_action_index,
                decision_temperature,
                log_prob,
            )
        self.core_stack_records.append(
            {
                "id": stack_id,
                "moduleId": str(candidate.module["id"]),
                "rotation": float(candidate.rotation.get("angle", 0.0)),
                "localAnchor": {
                    "x": float(candidate.anchor_x),
                    "y": float(candidate.anchor_y),
                },
                "floorCount": len(self.environments),
                "floorIndices": [environment.index for environment in self.environments],
                "placementIds": [placement["id"] for placement in placements],
                "locked": True,
                "decisionScope": "building",
                "logProbTerms": 1,
            }
        )
        self._prepared_initial_core_stacks = []
        return placements

    @staticmethod
    def _local_poly_signature(poly: Sequence[dict]) -> tuple[tuple[float, float], ...]:
        return tuple(
            (round(float(point["x"]), 6), round(float(point["y"]), 6))
            for point in poly
        )

    def _core_stacking_event(self) -> dict[str, Any]:
        """Build protocol metadata and independently audit every locked core."""

        enabled = not bool(self.settings["singleFloor"]) and len(self.environments) > 1
        if not enabled:
            disabled_status = (
                "disabled-single-floor"
                if bool(self.settings["singleFloor"])
                else "disabled-single-environment"
            )
            return {
                "enabled": False,
                "status": disabled_status,
                "mode": "disabled",
                "boundaryPolicy": "unchanged",
                "floorCount": len(self.environments),
                "siteResampleAttempts": 0,
                "initialCandidateCount": 0,
                "stackCount": 0,
                "lockedCoreCount": 0,
                "exactLocalAlignment": True,
                "violations": [],
                "stacks": [],
            }

        violations: list[str] = []
        locked_core_count = 0
        for environment in self.environments:
            for placement in environment.placements:
                if placement.get("category") != "core":
                    continue
                if not placement.get("coreStackLocked"):
                    violations.append(f"floor{environment.index}:unlockedCore:{placement['id']}")
                else:
                    locked_core_count += 1

        audited_stacks: list[dict[str, Any]] = []
        for record in self.core_stack_records:
            floor_placements: list[dict] = []
            for environment in self.environments:
                matches = [
                    placement
                    for placement in environment.placements
                    if placement.get("coreStackId") == record["id"]
                ]
                if len(matches) != 1:
                    violations.append(
                        f"{record['id']}:floor{environment.index}:count={len(matches)}"
                    )
                    continue
                floor_placements.append(matches[0])
            if floor_placements:
                reference = floor_placements[0]
                reference_poly = self._local_poly_signature(reference["poly"])
                for placement in floor_placements[1:]:
                    if placement.get("moduleId") != reference.get("moduleId"):
                        violations.append(f"{record['id']}:moduleMismatch")
                    if not math.isclose(
                        float(placement.get("rotation", 0.0)),
                        float(reference.get("rotation", 0.0)),
                        abs_tol=1.0e-6,
                    ):
                        violations.append(f"{record['id']}:rotationMismatch")
                    if placement.get("localAnchor") != reference.get("localAnchor"):
                        violations.append(f"{record['id']}:anchorMismatch")
                    if self._local_poly_signature(placement["poly"]) != reference_poly:
                        violations.append(f"{record['id']}:localPolygonMismatch")
            audited_stacks.append(dict(record))

        event = {
            **self.core_stacking_metadata,
            "enabled": True,
            "status": "locked" if self.core_stack_records else "ready",
            "floorCount": len(self.environments),
            "stackCount": len(self.core_stack_records),
            "lockedCoreCount": locked_core_count,
            "exactLocalAlignment": not violations,
            "violations": violations,
            "stacks": audited_stacks,
        }
        return event

    def _prepare_generation(
        self,
        settings: dict[str, Any],
        generation_id: int,
        episode: int,
    ) -> tuple[
        list[FloorEnvironment],
        list[dict],
        list[torch.Tensor],
        dict[str, Any],
        list[CoreStackCandidate],
    ]:
        attempt_limit = 1 if bool(settings["singleFloor"]) else CORE_SITE_TRANSACTION_ATTEMPTS
        for attempt in range(attempt_limit):
            environments, atrium_logs = self._build_sites(
                settings, generation_id, attempt=attempt
            )
            dictionary, shape_logs = self._synthesize_dictionary(
                settings, environments, generation_id, episode
            )
            for environment in environments:
                environment.reset(dictionary)
            if bool(settings["singleFloor"]):
                return (
                    environments,
                    dictionary,
                    atrium_logs + shape_logs,
                    {
                        "enabled": False,
                        "status": "disabled-single-floor",
                        "mode": "disabled",
                        "boundaryPolicy": "unchanged",
                        "siteResampleAttempts": 0,
                        "initialCandidateCount": 0,
                    },
                    [],
                )
            if len(environments) == 1:
                return (
                    environments,
                    dictionary,
                    atrium_logs + shape_logs,
                    {
                        "enabled": False,
                        "status": "disabled-single-environment",
                        "mode": "disabled",
                        "boundaryPolicy": "unchanged",
                        "siteResampleAttempts": 0,
                        "initialCandidateCount": 0,
                    },
                    [],
                )

            initial_stacks = self._shared_core_stack_candidates(
                0.0,
                environments=environments,
                dictionary=dictionary,
                settings=settings,
            )
            if initial_stacks:
                return (
                    environments,
                    dictionary,
                    atrium_logs + shape_logs,
                    {
                        "enabled": True,
                        "status": "ready",
                        "mode": "exact-shared-transform",
                        "boundaryPolicy": "whole-site-resample",
                        "siteResampleAttempts": attempt,
                        "initialCandidateCount": len(initial_stacks),
                    },
                    initial_stacks,
                )
        raise CoreStackingError(
            "no exact common core transform after "
            f"{attempt_limit} whole-site transactions; original boundary families were preserved"
        )

    def _commit_generation(
        self,
        settings: dict[str, Any],
        generation_id: int,
        environments: list[FloorEnvironment],
        dictionary: list[dict],
        shape_logs: list[torch.Tensor],
        core_stacking_metadata: dict[str, Any],
        initial_core_stacks: list[CoreStackCandidate],
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
        self.building_shape_log_probs = (
            [shape_logs[-1]]
            if bool(core_stacking_metadata.get("enabled")) and shape_logs
            else []
        )
        self.placement_log_probs = []
        self.core_stack_records = []
        self.core_stacking_metadata = dict(core_stacking_metadata)
        self._prepared_initial_core_stacks = list(initial_core_stacks)
        self.placement_log_probs_by_environment = {}
        self.placement_decisions = []
        self.step_number = 0
        self.step_profiler.reset()
        self._reset_episode_reward_telemetry()
        for group in self.optimizer.param_groups:
            group["lr"] = float(settings["learningRate"])

    def update_settings(self, patch: Any) -> dict[str, Any]:
        """Validate, prepare, and atomically commit settings plus a fresh site."""

        proposed = validate_settings_patch(self.settings, patch)
        generation = self.generation_id + 1
        prepared = self._prepare_generation(proposed, generation, self.episode)
        self._commit_generation(proposed, generation, *prepared)
        return self.site_event()

    def new_site(self) -> dict[str, Any]:
        """Atomically replace local sites while preserving learned policy state."""

        generation = self.generation_id + 1
        prepared = self._prepare_generation(
            self.settings, generation, self.episode
        )
        self._commit_generation(self.settings, generation, *prepared)
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
            prepared = self._prepare_generation(
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
        self.last_loss = 0.0
        self.last_actor_loss = 0.0
        self.last_value_loss = 0.0
        self.last_entropy = 0.0
        self.last_gradient_norm = 0.0
        self.last_advantage = 0.0
        self.generation_time_history.clear()
        self.frontier_growth_history.clear()
        self.generation_time_baseline = None
        self.frontier_growth_baseline = None
        self.baseline_transition_remaining = 0
        self.baseline_transition_anchor_reward = 0.0
        self.last_frontier_reward = 0.0
        self._commit_generation(self.settings, generation, *prepared)
        return self.site_event()

    def set_mode(self, mode: str) -> dict[str, Any]:
        """Switch between training and inference modes."""
        if mode not in ("training", "inference"):
            raise ValueError(f"unsupported mode: {mode}")
        self.mode = mode
        return {
            "type": "ack",
            "command": "setMode",
            "mode": self.mode,
            "message": f"mode switched to {self.mode}",
            "generationId": self.generation_id,
            "episode": self.episode,
        }

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
            "coreStacking": self._core_stacking_event(),
        }

    def _runtime_diagnostics(self) -> dict[str, Any]:
        """Return portable, lightweight backend and peak-memory telemetry."""

        peak_rss_bytes = 0
        try:
            import resource

            maximum_rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            peak_rss_bytes = maximum_rss if sys.platform == "darwin" else maximum_rss * 1024
        except (ImportError, OSError, ValueError):
            pass

        accelerator_allocated = 0
        accelerator_peak = 0
        try:
            if self.device.type == "cuda" and torch.cuda.is_available():
                accelerator_allocated = int(torch.cuda.memory_allocated(self.device))
                accelerator_peak = int(torch.cuda.max_memory_allocated(self.device))
            elif self.device.type == "mps" and hasattr(torch, "mps"):
                current = getattr(torch.mps, "current_allocated_memory", None)
                recommended = getattr(torch.mps, "recommended_max_memory", None)
                accelerator_allocated = int(current()) if callable(current) else 0
                accelerator_peak = int(recommended()) if callable(recommended) else 0
        except (RuntimeError, TypeError, ValueError):
            pass

        native_status = (
            G.native_geometry_status()
            if hasattr(G, "native_geometry_status")
            else {"available": False, "enabled": False, "loadError": "unsupported"}
        )
        return {
            "device": self.device.type,
            "nativeGeometry": native_status,
            "processPeakRssBytes": peak_rss_bytes,
            "acceleratorAllocatedBytes": accelerator_allocated,
            "acceleratorPeakBytes": accelerator_peak,
            "torchThreads": int(torch.get_num_threads()),
        }

    def site_event(self) -> dict[str, Any]:
        metrics = self._aggregate_online()
        diagnostics = self._runtime_diagnostics()
        metrics["runtimeDiagnostics"] = diagnostics
        return {
            "type": "site",
            "generationId": self.generation_id,
            "episode": self.episode,
            "device": self.device.type,
            "boundaries": [environment.world_boundary() for environment in self.environments],
            "dictionary": [_public_module(module) for module in self.dictionary],
            "metrics": metrics,
            "diagnostics": diagnostics,
            "scoreHistory": list(self.score_history),
            "bestScore": float(self.best_score),
            "coreStacking": self._core_stacking_event(),
        }

    def _aggregate_terminal(
        self,
        per_site: Sequence[dict[str, Any]],
        *,
        update_state: bool = True,
    ) -> dict[str, Any]:
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

        # Deep interior daylight penalty (per-floor averaged, un-diluted by site area, capped at 50.0 pts):
        # 1-hop room -> ~1.5 pts
        # 2-hop room -> ~8.0 pts
        # 3-hop room -> ~18.0 pts
        # 4-hop room -> ~30.0 pts
        # 5-hop room -> ~45.0 pts
        total_deep_rooms = sum(int(item.get("deepRoomCount", 0)) for item in per_site)
        avg_deep_rooms = total_deep_rooms / max(1, len(per_site))
        total_depth_score = math.fsum(float(item.get("depthPenaltyScore", 0.0)) for item in per_site)
        avg_depth_score_per_floor = total_depth_score / max(1, len(per_site))
        
        deep_room_ratio = _safe_ratio(
            math.fsum(float(item.get("deepRoomArea", 0.0)) for item in per_site),
            rentable,
        )
        deep_interior_penalty = min(50.0, avg_depth_score_per_floor)

        # Narrow facade chasm penalty (opposing exterior walls < 3.0m apart)
        total_chasm_len = math.fsum(float(item.get("facadeChasmOccludedLength", 0.0)) for item in per_site)
        avg_chasm_len = total_chasm_len / max(1, len(per_site))
        facade_chasm_ratio = _safe_ratio(total_chasm_len, perimeter)
        facade_chasm_penalty = min(30.0, 3.0 * avg_chasm_len)
        # Smooth continuous underfill penalty for premature stopping with too few shapes:
        # (35.0 pts max deduction for near-empty floors, smoothly ramping to 0.0 pts at fillRatio >= 0.40)
        underfill_deficit = max(0.0, 1.0 - (fill_ratio / 0.40))
        underfill_penalty = 35.0 * (underfill_deficit ** 2)

        raw_score = 100.0 * max(
            0.0,
            1.05 * scaled_fill
            + 0.15 * scaled_rentable
            + 0.10 * daylight
            + 0.02 * reuse
            + 0.02 * constructibility
            + 0.01 * envelope_efficiency
            - area_variance_penalty
            - partial_connection_penalty
            - (deep_interior_penalty / 100.0)
            - (facade_chasm_penalty / 100.0)
            - (underfill_penalty / 100.0),
        )
        multiplier_used = self.topology_multiplier
        topology_penalty = min(50.0, 100.0 * multiplier_used * violation_rate)
        score = raw_score - topology_penalty
        next_topology_multiplier = _clamp(
            self.topology_multiplier + 0.004 * (violation_rate - 0.02), 0.05, 0.15
        )
        if update_state:
            self.topology_multiplier = next_topology_multiplier
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
            "nextTopologyMultiplier": next_topology_multiplier,
            "rawScore": raw_score,
            "areaVariancePenalty": area_variance_penalty * 100.0,
            "deepRoomRatio": deep_room_ratio,
            "deepInteriorPenalty": deep_interior_penalty,
            "facadeChasmRatio": facade_chasm_ratio,
            "facadeChasmPenalty": facade_chasm_penalty,
            "underfillPenalty": underfill_penalty,
            "internalExposedPenalty": internal_exposed_penalty * 100.0,
            "partialConnectionPenalty": partial_connection_penalty * 100.0,
            "score": score,
            "perSite": list(per_site),
            "coreStacking": self._core_stacking_event(),
        }

    def _score_single_floor(
        self,
        item: dict[str, Any],
        area_variance_penalty: float = 0.0,
        shared_bonus: float = 0.0,
    ) -> float:
        """Compute the standalone reward score for a single floor rollout."""
        filled = float(item["filledArea"])
        site_area = float(item["siteArea"])
        rentable = float(item["rentableArea"])
        perimeter = float(item["exposedPerimeter"])
        fill_ratio = _safe_ratio(filled, site_area)
        rentable_ratio = _safe_ratio(rentable, filled)
        daylight = float(item.get("daylightRatio", 0.0))
        reuse = float(item.get("reuseRatio", 0.0))
        constructibility = float(item.get("constructibilityScore", 0.0))
        envelope_efficiency = float(item.get("envelopeEfficiency", 0.0))

        scaled_fill = max(0.0, 2.25 * fill_ratio - 0.75) if fill_ratio < 0.6 else fill_ratio
        scaled_rentable = max(0.0, (7.0 * rentable_ratio - 2.8) / 3.0) if rentable_ratio < 0.7 else rentable_ratio

        total_partial_len = float(item.get("totalPartialLength", 0.0))
        partial_connection_penalty = 0.04 * _safe_ratio(total_partial_len, perimeter)

        deep_interior_penalty = min(50.0, float(item.get("depthPenaltyScore", 0.0)))
        facade_chasm_penalty = min(30.0, 3.0 * float(item.get("facadeChasmOccludedLength", 0.0)))

        underfill_deficit = max(0.0, 1.0 - (fill_ratio / 0.40))
        underfill_penalty = 35.0 * (underfill_deficit ** 2)

        raw_score = 100.0 * max(
            0.0,
            1.05 * scaled_fill
            + 0.15 * scaled_rentable
            + 0.10 * daylight
            + 0.02 * reuse
            + 0.02 * constructibility
            + 0.01 * envelope_efficiency
            - area_variance_penalty
            - partial_connection_penalty
            - (deep_interior_penalty / 100.0)
            - (facade_chasm_penalty / 100.0)
            - (underfill_penalty / 100.0),
        )

        violation_rate = 0.0 if item.get("topologyValid", False) else (1.0 + 0.08 * len(item.get("topologyViolations", [])))
        topology_penalty = min(50.0, 100.0 * self.topology_multiplier * violation_rate)
        return raw_score - topology_penalty + shared_bonus

    def _try_place_new_module(
        self,
        environment: FloorEnvironment,
        module: dict,
        orientation_basis: float,
        per_environment_limit: int,
        temperature: float,
    ) -> dict | None:
        """Validate, publish, sample, and place one newly synthesized module."""

        candidates = environment.generate_candidates_for_module(
            module,
            self.settings,
            orientation_basis,
            profiler=self.step_profiler,
            limit=per_environment_limit,
            category_filter=("room",)
            if not bool(self.settings["singleFloor"]) and len(self.environments) > 1
            else None,
        )
        if not bool(self.settings["singleFloor"]) and len(self.environments) > 1:
            # Exact multi-floor cores are exclusively owned by the shared
            # building gate; a shape-repair path must never create one locally.
            candidates = [
                candidate
                for candidate in candidates
                if candidate.module.get("category") != "core"
            ]
        if not candidates:
            return None
        self.dictionary.append(module)
        for peer in self.environments:
            if module not in peer.dictionary:
                peer.dictionary.append(module)
                peer.module_uses[module["id"]] = 0

        features = [candidate.features for candidate in candidates]
        feature_tensor = torch.tensor(
            features, dtype=torch.float32, device=self.device
        )
        with torch.no_grad():
            logits = torch.nan_to_num(
                self.model.placement_logits(feature_tensor),
                nan=0.0,
                posinf=20.0,
                neginf=-20.0,
            ).clamp(-30.0, 30.0) / temperature
        distribution = torch.distributions.Categorical(logits=logits)
        selected = distribution.sample()
        selected_offset = int(selected.item())
        self._record_placement_decision(
            environment.index,
            features,
            selected_offset,
            temperature,
            distribution.log_prob(selected),
        )
        return environment.place(candidates[selected_offset])

    def _record_placement_log_prob(
        self,
        environment_index: int,
        log_prob: torch.Tensor,
    ) -> None:
        self.placement_log_probs.append(log_prob)
        self.placement_log_probs_by_environment.setdefault(environment_index, []).append(log_prob)

    def _record_placement_decision(
        self,
        environment_index: int,
        features: Sequence[Sequence[float]],
        action_index: int,
        temperature: float,
        sampled_log_prob: torch.Tensor,
        positions: Sequence[Sequence[float]] | None = None,
        angles: Sequence[float] | None = None,
    ) -> None:
        self._record_placement_log_prob(environment_index, sampled_log_prob.detach().cpu())
        pos_t = torch.tensor(positions, dtype=torch.float32) if positions is not None else None
        ang_t = torch.tensor(angles, dtype=torch.float32) if angles is not None else None
        self.placement_decisions.append(
            PlacementPolicyDecision(
                environment_index=environment_index,
                features=torch.tensor(features, dtype=torch.float32),
                action_index=int(action_index),
                temperature=float(temperature),
                old_log_prob=float(sampled_log_prob.detach().cpu().item()),
                positions=pos_t,
                angles=ang_t,
            )
        )

    def _extract_episode_diversity_embedding(self, metrics: dict[str, Any]) -> list[float]:
        """Extract a continuous 5D geometric morphology embedding for DPP diversity."""
        fill = float(metrics.get("fillRatio", 0.5))
        rentable = float(metrics.get("rentableRatio", 0.5))
        comp = float(metrics.get("compactness", 0.5))
        vocab = float(metrics.get("vocabSize", 10)) / 30.0
        entropy = float(metrics.get("utilizationEntropyBonus", 0.0)) / 2.0
        return [fill, rentable, comp, vocab, entropy]

    def _compute_dpp_diversity_bonus(self, current_embedding: list[float], current_score: float) -> float:
        """Compute the calibrated log det(S) diversity volume bonus from the historical archive."""
        if len(self.diversity_archive) < 2:
            self.diversity_archive.append((current_embedding, current_score))
            return 0.0

        all_embeddings = [emb for emb, _ in self.diversity_archive] + [current_embedding]
        self.diversity_archive.append((current_embedding, current_score))

        N = len(all_embeddings)
        feat_tensor = torch.tensor(all_embeddings, dtype=torch.float32)
        diff = feat_tensor.unsqueeze(1) - feat_tensor.unsqueeze(0)
        dist_sq = (diff ** 2).sum(dim=-1)
        sigma = 0.5
        eps = 1.0e-3
        S = torch.exp(-dist_sq / (2.0 * (sigma ** 2)))
        S_reg = S + torch.eye(N) * eps

        sign, logdet = torch.linalg.slogdet(S_reg)
        if sign.item() <= 0:
            return 0.0

        min_logdet = math.log(N + eps) + (N - 1) * math.log(eps)
        raw_logdet = float(logdet.item())
        diversity_nats = max(0.0, (raw_logdet - min_logdet) / N)
        return float(diversity_nats)


    def _learn_from_episode(
        self,
        score: float,
        per_floor_scores: Sequence[float] | None = None,
    ) -> None:
        normalized_score = score / 100.0
        if per_floor_scores is not None and len(per_floor_scores) == len(self.environments):
            floor_targets = [s / 100.0 for s in per_floor_scores]
        else:
            floor_targets = [normalized_score] * max(1, len(self.environments))

        gamma = 0.99
        gae_lambda = 0.95
        clip_eps = 0.2

        floor_descriptors = self._site_descriptor(self.environments, self.settings)
        if not floor_descriptors:
            floor_descriptors = [[0.0] * FLOOR_DESCRIPTOR_DIM]
        floor_tensor = torch.tensor(floor_descriptors, dtype=torch.float32, device=self.device)
        pooled_site = self.model.encode_sites(floor_tensor)
        value_prediction = self.model.value(pooled_site)
        v_pred_val = float(value_prediction.detach().cpu().item())
        target = torch.tensor(normalized_score, dtype=torch.float32, device=self.device)

        policy_loss_terms: list[torch.Tensor] = []
        entropy_terms: list[torch.Tensor] = []

        if self.placement_decisions:
            # 1. Compute GAE advantages per trajectory / environment using individual floor scores
            grouped_decisions: dict[int, list[PlacementPolicyDecision]] = {}
            for decision in self.placement_decisions:
                grouped_decisions.setdefault(decision.environment_index, []).append(decision)

            decision_advantages: list[float] = []
            for env_idx, env_decisions in sorted(grouped_decisions.items()):
                t_steps = len(env_decisions)
                floor_target = floor_targets[env_idx] if env_idx < len(floor_targets) else normalized_score
                gae = 0.0
                env_advs = [0.0] * t_steps
                for t in reversed(range(t_steps)):
                    step_reward = floor_target if t == t_steps - 1 else 0.0
                    v_next = 0.0 if t == t_steps - 1 else v_pred_val
                    delta = step_reward + gamma * v_next - v_pred_val
                    gae = delta + gamma * gae_lambda * gae
                    env_advs[t] = gae
                decision_advantages.extend(env_advs)

            adv_tensor = torch.tensor(decision_advantages, dtype=torch.float32, device=self.device)
            # Batch advantage normalization across the parallel floor rollouts:
            # Rewards actions from high-scoring floors and penalizes actions from low-scoring floors
            if len(adv_tensor) > 1 and float(adv_tensor.std().item()) > 1.0e-6:
                norm_adv = (adv_tensor - adv_tensor.mean()) / (adv_tensor.std() + 1.0e-8)
            else:
                norm_adv = adv_tensor

            # 2. PPO Clipped Surrogate Loss
            for idx, decision in enumerate(self.placement_decisions):
                features = decision.features.to(self.device)
                positions = (
                    decision.positions.to(self.device)
                    if decision.positions is not None
                    else None
                )
                angles = (
                    decision.angles.to(self.device)
                    if decision.angles is not None
                    else None
                )

                group_logits = (
                    torch.nan_to_num(
                        self.model.placement_logits(features, positions, angles),
                        nan=0.0,
                        posinf=20.0,
                        neginf=-20.0,
                    ).clamp(-30.0, 30.0)
                    / decision.temperature
                )

                count = int(features.shape[0])
                group_log_probs = F.log_softmax(group_logits, dim=0)
                selected_log_prob = group_log_probs[decision.action_index]
                old_log_prob = torch.tensor(
                    decision.old_log_prob, dtype=torch.float32, device=self.device
                )

                # Probability ratio r_t(theta)
                ratio = torch.exp(selected_log_prob - old_log_prob)
                adv = norm_adv[idx]
                surr1 = ratio * adv
                surr2 = torch.clamp(ratio, 1.0 - clip_eps, 1.0 + clip_eps) * adv
                policy_loss_terms.append(-torch.min(surr1, surr2))

                if count > 1:
                    probabilities = group_log_probs.exp()
                    entropy_terms.append(
                        -(probabilities * group_log_probs).sum() / math.log(count)
                    )

            actor_loss = torch.stack(policy_loss_terms).mean() if policy_loss_terms else torch.zeros((), dtype=torch.float32, device=self.device)
        elif self.placement_log_probs_by_environment:
            trajectory_term = _mean_trajectory_log_probability(
                self.placement_log_probs_by_environment
            )
            actor_loss = -((normalized_score - v_pred_val) * trajectory_term) if trajectory_term is not None else torch.zeros((), dtype=torch.float32, device=self.device)
        elif self.placement_log_probs:
            actor_loss = -((normalized_score - v_pred_val) * torch.stack(self.placement_log_probs).sum())
        else:
            actor_loss = torch.zeros((), dtype=torch.float32, device=self.device)

        building_shape_ids = {
            id(log_probability)
            for log_probability in self.building_shape_log_probs
        }
        floor_shape_log_probs = [
            log_probability
            for log_probability in self.shape_log_probs
            if id(log_probability) not in building_shape_ids
        ]
        if floor_shape_log_probs:
            actor_loss = actor_loss - (
                0.8
                * (normalized_score - v_pred_val)
                * torch.stack(floor_shape_log_probs).sum()
                / max(1, len(self.environments))
            )
        if self.building_shape_log_probs:
            actor_loss = actor_loss - (
                0.8
                * (normalized_score - v_pred_val)
                * torch.stack(self.building_shape_log_probs).sum()
            )

        value_loss = F.smooth_l1_loss(value_prediction, target)
        entropy = (
            torch.stack(entropy_terms).mean()
            if entropy_terms
            else torch.zeros((), dtype=torch.float32, device=self.device)
        )
        loss = actor_loss + 0.5 * value_loss - 0.01 * entropy
        self.optimizer.zero_grad(set_to_none=True)
        loss.backward()
        gradient_norm = nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=2.0)
        self.optimizer.step()
        self.last_loss = float(loss.detach().cpu().item())
        self.last_actor_loss = float(actor_loss.detach().cpu().item())
        self.last_value_loss = float(value_loss.detach().cpu().item())
        self.last_entropy = float(entropy.detach().cpu().item())
        self.last_gradient_norm = float(torch.as_tensor(gradient_norm).detach().cpu().item())
        self.last_advantage = float(normalized_score - v_pred_val)
        self.baseline = 0.90 * self.baseline + 0.10 * normalized_score

    def _finish_episode(self) -> dict[str, Any]:
        episode_start_time = getattr(self, "episode_start_time", time.perf_counter())
        completed_episode = self.episode
        completed_core_stacking = self._core_stacking_event()
        
        terminal_metrics_start = time.perf_counter()
        per_site = [
            environment.terminal_metrics(
                bool(self.settings["singleFloor"]), float(self.settings["coreSpacing"])
            )
            for environment in self.environments
        ]
        self.step_profiler.record("terminalMetrics", time.perf_counter() - terminal_metrics_start)
        
        aggregate_terminal_start = time.perf_counter()
        metrics = self._aggregate_terminal(per_site)
        self.step_profiler.record("aggregateTerminal", time.perf_counter() - aggregate_terminal_start)
        
        # 1. Run BPE merging
        episode_bpe_merge_start = time.perf_counter()
        layout_graphs = []
        for idx, environment in enumerate(self.environments):
            layout_graphs.append(graph.extract_layout_graph(environment.placements, idx))
            
        merged_vocab, bpe_stats = graph.bpe_merge(
            layout_graphs,
            min_frequency=2,
            max_rounds=20,
            max_vocab_size=max(0, 30 - len(self.dictionary))
        )
        reused_bpe_modules, bpe_bonus = _reused_bpe_module_summary(layout_graphs, episode=self.episode)
            
        # Count top-level post-merge triangles from polygon geometry, then apply
        # the canonical -8 points per average unmerged triangle per floor.
        post_merge_triangles = graph.count_post_merge_triangles(layout_graphs)
        unmerged_triangles = len(post_merge_triangles)
        unmerged_triangle_penalty = _average_unmerged_triangle_penalty(
            unmerged_triangles, len(layout_graphs)
        )
        self.step_profiler.record("episodeBpeMerge", time.perf_counter() - episode_bpe_merge_start)

        # Phase 1C: Primitive Purging & Uniform Module Utilization Entropy Reward
        active_shape_types = {
            node.get("shapeType", "")
            for layout_graph in layout_graphs
            for node in layout_graph.nodes.values()
        }
        # Purge fully-consumed primitive shapes that have 0 unmerged placements
        purged_dictionary = [
            module for module in self.dictionary
            if module["id"] in active_shape_types or module.get("category") == "core"
        ]

        # Calculate module utilization Shannon entropy across placed modules
        placed_shape_counts = Counter(
            node.get("shapeType", "")
            for layout_graph in layout_graphs
            for node in layout_graph.nodes.values()
        )
        total_placed = sum(placed_shape_counts.values())
        if total_placed > 0 and len(placed_shape_counts) > 1:
            usage_probs = [cnt / total_placed for cnt in placed_shape_counts.values() if cnt > 0]
            shannon_h = -sum(p * math.log(p) for p in usage_probs)
            max_h = math.log(len(placed_shape_counts))
            utilization_entropy = shannon_h / max_h if max_h > 1.0e-6 else 0.0
            utilization_entropy_bonus = 2.0 * utilization_entropy
        else:
            utilization_entropy_bonus = 0.0

        # Dictionary Limit Breach Squared Penalty (ramping penalty multiplier, capped at 80.0 points max)
        dict_limit = int(self.settings["dictCap"])
        prelim_vocab_size = len(purged_dictionary) if purged_dictionary else len(self.dictionary)
        dict_limit_breach = max(0, prelim_vocab_size - dict_limit)
        breach_multiplier = 5.0 + 15.0 * min(1.0, float(self.episode) / 100.0)
        dict_breach_penalty = min(80.0, float(dict_limit_breach ** 2) * breach_multiplier)

        # 2. Apply BPE bonus, utilization entropy, unmerged triangle penalty, and dict breach penalty to score
        frontier_metrics = self._relative_frontier_reward()
        score = (
            float(metrics["score"])
            + bpe_bonus
            + utilization_entropy_bonus
            - unmerged_triangle_penalty
            + float(frontier_metrics["relativeTimeReward"])
            - dict_breach_penalty
        )
        metrics["score"] = f"{score:.4f}"
        metrics["dictBreachPenalty"] = dict_breach_penalty
        metrics["dictLimitBreach"] = dict_limit_breach
        metrics["vocabSize"] = bpe_stats["unique_types"]
        metrics["totalPlacements"] = bpe_stats["total_placements"]
        metrics["bpeRounds"] = bpe_stats["merge_rounds"]
        metrics["reusedBpeModules"] = reused_bpe_modules
        metrics["bpeBonus"] = bpe_bonus
        metrics["utilizationEntropyBonus"] = utilization_entropy_bonus
        metrics["unmergedTriangles"] = unmerged_triangles
        metrics["averageUnmergedTriangles"] = unmerged_triangles / max(1, len(layout_graphs))
        metrics["unmergedTrianglePenalty"] = unmerged_triangle_penalty
        metrics.update(frontier_metrics)
        # Phase 1G: DPP Determinantal Typological Diversity
        embedding = self._extract_episode_diversity_embedding(metrics)
        dpp_bonus = self._compute_dpp_diversity_bonus(embedding, score)
        self.last_dpp_diversity = dpp_bonus
        metrics["dppDiversityBonus"] = round(dpp_bonus, 4)


        # Compute standalone scores per individual floor rollout
        shared_bonus = (
            bpe_bonus
            + utilization_entropy_bonus
            - unmerged_triangle_penalty
            + float(frontier_metrics["relativeTimeReward"])
            - dict_breach_penalty
        )
        dict_areas = [G.polygon_area(m["poly"]) for m in self.dictionary]
        mean_dict_area = _mean(dict_areas) if dict_areas else 1.0
        cv = _safe_ratio(_std(dict_areas), max(1.0, mean_dict_area)) if dict_areas else 0.0
        area_variance_penalty = _clamp(0.05 * cv, 0.0, 0.15)

        per_floor_scores = [
            self._score_single_floor(ps, area_variance_penalty=area_variance_penalty, shared_bonus=shared_bonus)
            for ps in per_site
        ]
        metrics["perFloorScores"] = [round(s, 2) for s in per_floor_scores]

        # 3. Learn from updated score (only in training mode)
        if getattr(self, "mode", "training") == "training":

            learning_start = time.perf_counter()
            self._learn_from_episode(score, per_floor_scores=per_floor_scores)
            self.step_profiler.record("learning", time.perf_counter() - learning_start)
            metrics["policyLoss"] = self.last_loss
            metrics["actorLoss"] = self.last_actor_loss
            metrics["valueLoss"] = self.last_value_loss
            metrics["policyEntropy"] = self.last_entropy
            metrics["gradientNorm"] = self.last_gradient_norm
            metrics["advantage"] = self.last_advantage
            metrics["learningRate"] = float(self.optimizer.param_groups[0]["lr"])
            metrics["learningAlgorithm"] = "ppo_gae"
        else:
            metrics["policyLoss"] = 0.0
            metrics["actorLoss"] = 0.0
            metrics["valueLoss"] = 0.0
            metrics["policyEntropy"] = 0.0
            metrics["gradientNorm"] = 0.0
            metrics["advantage"] = 0.0
            metrics["learningRate"] = 0.0
            metrics["learningAlgorithm"] = "inference_only"

        metrics["baseline"] = self.baseline
        self.score_history.append(score)
        self.best_score = max(self.best_score, score)

        episode_formatting_start = time.perf_counter()
        completed_dictionary_formatted = [
            _public_module(module) for module in self.dictionary
        ]
        individual_placements_formatted = []
        for env_idx, environment in enumerate(self.environments):
            dx, dy = environment.offset
            for placement in environment.placements:
                world_poly = G.translate_polygon(placement["poly"], dx, dy)
                formatted_placement = {
                    "id": placement["id"],
                    "poly": world_poly,
                    "instanceIdx": env_idx,
                    "center": G.polygon_centroid(world_poly),
                    "category": placement.get("category", "room"),
                    "module": {
                        "id": placement.get("shapeType", placement.get("moduleId", placement["id"])),
                        "category": placement.get("category", "room"),
                    },
                }
                if placement.get("coreStackLocked"):
                    stack_fields = {
                        "coreStackId": placement["coreStackId"],
                        "coreStackLocked": True,
                        "coreStackTriggerFloor": placement.get("coreStackTriggerFloor"),
                        "localAnchor": dict(placement["localAnchor"]),
                    }
                    formatted_placement.update(stack_fields)
                    formatted_placement["module"].update(stack_fields)
                individual_placements_formatted.append(formatted_placement)
        self.step_profiler.record("episodeFormatting", time.perf_counter() - episode_formatting_start)

        self.episode += 1
        dict_synthesis_start = time.perf_counter()
        next_initial_stacks: list[CoreStackCandidate] = []
        if not bool(self.settings["singleFloor"]) and len(self.environments) > 1:
            # Keep the already-proven learned core across episodes on this site.
            # New room vocabulary remains dynamic, but a later episode can never
            # enter an unvalidated partial-core state.
            primary_core = next(
                (
                    module
                    for module in self.dictionary
                    if module.get("category") == "core"
                ),
                None,
            )
            if primary_core is None:
                raise CoreStackingError("completed multi-floor episode lost its primary core module")
            next_dictionary = [primary_core]
            next_shape_logs = []
            empty_floors: list[FloorEnvironment] = []
            for environment in self.environments:
                empty = FloorEnvironment(
                    environment.index,
                    environment.boundary,
                    environment.atrium_choice,
                    environment.site,
                    environment.offset,
                    G.RNG(
                        int(self.settings["seed"])
                        + self.generation_id * 104729
                        + self.episode * 65537
                        + environment.index * 8191
                    ),
                )
                empty.reset(next_dictionary)
                empty_floors.append(empty)
            next_basis = (
                0.0
                if float(self.settings["angleStep"]) <= 0.0
                else (self.episode * float(self.settings["angleStep"]) * 3.0) % 180.0
            )
            preflight = self._shared_core_stack_candidates(
                next_basis,
                environments=empty_floors,
                dictionary=next_dictionary,
                settings=self.settings,
            )
            if not preflight:
                raise CoreStackingError(
                    "the proven core failed empty-floor prevalidation for the next episode"
                )
        else:
            next_dictionary, next_shape_logs = self._synthesize_dictionary(
                self.settings, self.environments, self.generation_id, self.episode
            )
        self.step_profiler.record("dictSynthesis", time.perf_counter() - dict_synthesis_start)
        self.dictionary = next_dictionary
        self.shape_log_probs = next_shape_logs
        self.building_shape_log_probs = []
        self.placement_log_probs = []
        self.core_stack_records = []
        self.placement_log_probs_by_environment = {}
        self.placement_decisions = []
        self.step_number = 0
        for environment in self.environments:
            environment.reset(next_dictionary)
        if not bool(self.settings["singleFloor"]) and len(self.environments) > 1:
            next_initial_stacks = self._shared_core_stack_candidates(next_basis)
            if not next_initial_stacks:
                raise CoreStackingError("next episode lost its prevalidated core transforms")
            self.core_stacking_metadata = {
                **self.core_stacking_metadata,
                "enabled": True,
                "status": "ready",
                "initialCandidateCount": len(next_initial_stacks),
            }
        else:
            self.core_stacking_metadata = {
                "enabled": False,
                "status": "disabled-single-floor",
                "mode": "disabled",
                "boundaryPolicy": "unchanged",
                "siteResampleAttempts": 0,
                "initialCandidateCount": 0,
            }
        self._prepared_initial_core_stacks = next_initial_stacks
        self._reset_episode_reward_telemetry()
            
        # 4. Format merged placements for rendering
        episode_formatting_start2 = time.perf_counter()
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
        self.step_profiler.record("episodeFormatting", time.perf_counter() - episode_formatting_start2)

        self.step_profiler.record("episodeTotal", time.perf_counter() - episode_start_time)
        metrics["performanceTimings"] = self.step_profiler.summary()
        diagnostics = self._runtime_diagnostics()
        metrics["runtimeDiagnostics"] = diagnostics
        self.step_profiler.reset()
        if hasattr(self, "episode_start_time"):
            delattr(self, "episode_start_time")

        event = {
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
            "coreStacking": completed_core_stacking,
            "nextCoreStacking": self._core_stacking_event(),
            "diagnostics": diagnostics,
        }

        if getattr(self, "mode", "training") == "inference" or bool(self.settings.get("recordTrajectories", False)):
            record_dataset_trajectory(event)

        return event

    def step(self, generation_id: Any, episode: Any) -> dict[str, Any]:
        """Advance active floors while keeping cores as one building action."""

        step_start_time = time.perf_counter()
        if self.step_number == 0 or not hasattr(self, "episode_start_time"):
            self.episode_start_time = step_start_time

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
        orientation_basis = (
            0.0
            if angle_step <= 0.0
            else (self.episode * angle_step * 3.0) % 180.0
        )
        multi_floor = (
            not bool(self.settings["singleFloor"])
            and len(self.environments) > 1
        )
        core_presence = [bool(environment.core_ids) for environment in self.environments]
        if multi_floor and any(core_presence) and not all(core_presence):
            raise CoreStackingError("partial core state detected before building action")
        initial_core_required = multi_floor and not any(core_presence)

        shared_stacks: list[CoreStackCandidate] = []
        if multi_floor:
            if initial_core_required and self._prepared_initial_core_stacks:
                for prepared_stack in self._prepared_initial_core_stacks:
                    revalidated = self._core_stack_at_transform(
                        self.environments,
                        prepared_stack.module,
                        prepared_stack.rotation,
                        prepared_stack.anchor_x,
                        prepared_stack.anchor_y,
                        self.settings,
                        orientation_basis,
                    )
                    if revalidated is not None:
                        shared_stacks.append(revalidated)
            if not shared_stacks:
                shared_stacks = self._shared_core_stack_candidates(orientation_basis)
            if initial_core_required and not shared_stacks:
                raise CoreStackingError(
                    "the prevalidated first core has no exact transform on every floor"
                )

        candidate_groups: list[tuple[FloorEnvironment, list[PlacementCandidate]]] = []
        all_features: list[list[float]] = []
        per_environment_limit = max(12, 48 // max(1, len(self.environments)))
        active_environments: list[FloorEnvironment] = []
        for environment in self.environments:
            if environment.done:
                continue
            if len(environment.placements) >= int(self.settings["maxModules"]):
                environment.done = True
                continue
            if initial_core_required:
                # The first multi-floor action is indivisible and mandatory.
                continue
            active_environments.append(environment)

        def generate_for_environment(
            environment: FloorEnvironment,
        ) -> tuple[FloorEnvironment, list[PlacementCandidate], float]:
            generation_started = time.perf_counter()
            candidates = environment.generate_candidates(
                self.settings,
                orientation_basis,
                limit=per_environment_limit,
                profiler=self.step_profiler,
                allow_core=not multi_floor,
            )
            if multi_floor:
                # Floor-local trajectories never own core actions.
                candidates = [
                    candidate
                    for candidate in candidates
                    if candidate.module.get("category") != "core"
                ]
            return environment, candidates, time.perf_counter() - generation_started

        if len(active_environments) > 1:
            generated = list(
                self.executor.map(generate_for_environment, active_environments)
            )
        else:
            generated = [
                generate_for_environment(environment)
                for environment in active_environments
            ]

        for environment, candidates, candidate_generation_duration in generated:
            self.step_profiler.record(
                "candidateGeneration", candidate_generation_duration
            )
            self._record_frontier_sample(environment, candidate_generation_duration)
            if not candidates:
                continue
            candidate_groups.append((environment, candidates))
            all_features.extend(candidate.features for candidate in candidates)

        if not candidate_groups and not shared_stacks:
            return self._finish_episode()

        temperature = max(0.32, 0.90 * math.exp(-self.episode / 45.0))
        placements: list[dict] = []
        stack_selected = False

        if shared_stacks:
            gate_actions: list[CoreStackCandidate | None] = []
            gate_features: list[list[float]] = []
            if candidate_groups and not initial_core_required:
                floor_alternatives = [
                    _mean_feature_rows(
                        candidate.features for candidate in candidates
                    )
                    for _, candidates in candidate_groups
                ]
                gate_actions.append(None)
                gate_features.append(_mean_feature_rows(floor_alternatives))
            gate_actions.extend(shared_stacks)
            gate_features.extend(stack.features for stack in shared_stacks)
            gate_tensor = torch.tensor(
                gate_features, dtype=torch.float32, device=self.device
            )
            gate_started = time.perf_counter()
            with torch.no_grad():
                gate_logits = torch.nan_to_num(
                    self.model.placement_logits(gate_tensor),
                    nan=0.0,
                    posinf=20.0,
                    neginf=-20.0,
                ).clamp(-30.0, 30.0) / temperature
            gate_distribution = torch.distributions.Categorical(logits=gate_logits)
            gate_index = gate_distribution.sample()
            gate_offset = int(gate_index.item())
            gate_log_prob = gate_distribution.log_prob(gate_index)
            self.step_profiler.record(
                "policyInference", time.perf_counter() - gate_started
            )
            selected_stack = gate_actions[gate_offset]
            if selected_stack is not None:
                placement_started = time.perf_counter()
                placements.extend(
                    self._commit_core_stack(
                        selected_stack,
                        gate_log_prob,
                        orientation_basis,
                        decision_features=gate_features,
                        decision_action_index=gate_offset,
                        decision_temperature=temperature,
                    )
                )
                self.step_profiler.record(
                    "placement", time.perf_counter() - placement_started
                )
                stack_selected = True
            else:
                self._record_placement_decision(
                    BUILDING_TRAJECTORY_INDEX,
                    gate_features,
                    gate_offset,
                    temperature,
                    gate_log_prob,
                )

        if not stack_selected:
            if not candidate_groups:
                return self._finish_episode()

            inference_started = time.perf_counter()
            for environment, candidates in candidate_groups:
                c_feats = torch.tensor(
                    [c.features for c in candidates],
                    dtype=torch.float32,
                    device=self.device,
                )
                c_pos = torch.tensor(
                    [(c.anchor_x, c.anchor_y) for c in candidates],
                    dtype=torch.float32,
                    device=self.device,
                )
                c_ang = torch.tensor(
                    [float(c.rotation.get("angle", 0.0)) for c in candidates],
                    dtype=torch.float32,
                    device=self.device,
                )

                with torch.no_grad():
                    group_logits = (
                        torch.nan_to_num(
                            self.model.placement_logits(c_feats, c_pos, c_ang),
                            nan=0.0,
                            posinf=20.0,
                            neginf=-20.0,
                        ).clamp(-30.0, 30.0)
                        / temperature
                    )

                distribution = torch.distributions.Categorical(logits=group_logits)
                selected_index = distribution.sample()
                selected_offset = int(selected_index.item())
                selected_candidate = candidates[selected_offset]
                self._record_placement_decision(
                    environment.index,
                    [c.features for c in candidates],
                    selected_offset,
                    temperature,
                    distribution.log_prob(selected_index),
                    positions=[(c.anchor_x, c.anchor_y) for c in candidates],
                    angles=[float(c.rotation.get("angle", 0.0)) for c in candidates],
                )

                if selected_candidate.module["id"] == "stop":
                    environment.done = True
                    continue
                if selected_candidate.module["id"] == "create_new":
                    slot_index = len(self.dictionary)
                    placed = False
                    synthesis_started = time.perf_counter()
                    for _attempt in range(2):
                        try:
                            new_module, shape_log_prob = self._sample_custom_shape(
                                self.settings, self.environments, slot_index
                            )
                            # Sampling the shape is a real decision even if its
                            # placement mask is empty.
                            self.shape_log_probs.append(shape_log_prob)
                            placement = self._try_place_new_module(
                                environment,
                                new_module,
                                orientation_basis,
                                per_environment_limit,
                                temperature,
                            )
                            if placement is not None:
                                placements.append(placement)
                                placed = True
                                break
                        except ValueError:
                            continue

                    if not placed:
                        fallback_candidates = [
                            candidate
                            for candidate in candidates
                            if candidate.module["id"] not in ("create_new", "stop")
                        ]
                        if fallback_candidates:
                            fallback_features = [
                                candidate.features
                                for candidate in fallback_candidates
                            ]
                            fallback_pos = [
                                (c.anchor_x, c.anchor_y) for c in fallback_candidates
                            ]
                            fallback_ang = [
                                float(c.rotation.get("angle", 0.0))
                                for c in fallback_candidates
                            ]
                            fallback_tensor = torch.tensor(
                                fallback_features,
                                dtype=torch.float32,
                                device=self.device,
                            )
                            pos_tensor = torch.tensor(
                                fallback_pos,
                                dtype=torch.float32,
                                device=self.device,
                            )
                            ang_tensor = torch.tensor(
                                fallback_ang,
                                dtype=torch.float32,
                                device=self.device,
                            )
                            with torch.no_grad():
                                fallback_logits = (
                                    torch.nan_to_num(
                                        self.model.placement_logits(
                                            fallback_tensor, pos_tensor, ang_tensor
                                        ),
                                        nan=0.0,
                                        posinf=20.0,
                                        neginf=-20.0,
                                    ).clamp(-30.0, 30.0)
                                    / temperature
                                )
                            fallback_distribution = torch.distributions.Categorical(
                                logits=fallback_logits
                            )
                            fallback_index = fallback_distribution.sample()
                            fallback_offset = int(fallback_index.item())
                            self._record_placement_decision(
                                environment.index,
                                fallback_features,
                                fallback_offset,
                                temperature,
                                fallback_distribution.log_prob(fallback_index),
                                positions=fallback_pos,
                                angles=fallback_ang,
                            )
                            placements.append(
                                environment.place(
                                    fallback_candidates[fallback_offset]
                                )
                            )
                            placed = True
                        else:
                            if environment.placements:
                                for repair_module in self._frontier_compatible_modules(
                                    self.settings, environment, slot_index
                                ):
                                    placement = self._try_place_new_module(
                                        environment,
                                        repair_module,
                                        orientation_basis,
                                        per_environment_limit,
                                        temperature,
                                    )
                                    if placement is not None:
                                        placements.append(placement)
                                        placed = True
                                        break
                            if not placed:
                                environment.consecutive_proposal_failures += 1
                                environment.done = (
                                    environment.consecutive_proposal_failures
                                    >= MAX_CONSECUTIVE_PROPOSAL_FAILURES
                                )
                    self.step_profiler.record(
                        "shapeSynthesis", time.perf_counter() - synthesis_started
                    )
                else:
                    placement_started = time.perf_counter()
                    placements.append(environment.place(selected_candidate))
                    self.step_profiler.record(
                        "placement", time.perf_counter() - placement_started
                    )

                if len(environment.placements) >= int(self.settings["maxModules"]):
                    environment.done = True

        for environment in self.environments:
            if len(environment.placements) >= int(self.settings["maxModules"]):
                environment.done = True

        self.step_number += 1
        # BPE remains terminal/evaluate-only; rebuilding on every delta is
        # quadratic and does not affect transitions.
        merged_vocab: list[graph.MergedModule] = []
        merged_placements_formatted: list[dict[str, Any]] = []
        self.step_profiler.record("bpeMerge", 0.0)
        self.step_profiler.record("stepTotal", time.perf_counter() - step_start_time)
        metrics = self._aggregate_online()
        metrics["performanceTimings"] = self.step_profiler.summary()
        diagnostics = self._runtime_diagnostics()
        metrics["runtimeDiagnostics"] = diagnostics

        return {
            "type": "placements",
            "generationId": self.generation_id,
            "episode": self.episode,
            "step": self.step_number,
            "placements": placements,
            "mergedPlacements": merged_placements_formatted,
            "mergedDictionary": [
                _public_merged_module(module) for module in merged_vocab
            ],
            "dictionary": [_public_module(module) for module in self.dictionary],
            "metrics": metrics,
            "coreStacking": self._core_stacking_event(),
            "diagnostics": diagnostics,
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
            max_vocab_size=max(0, 30 - len(self.dictionary))
        )
        
        # 2. Compute terminal metrics
        single_floor = self.settings.get("singleFloor", False)
        core_spacing = float(self.settings.get("coreSpacing", 8.0))
        per_site = [
            environment.terminal_metrics(single_floor, core_spacing)
            for environment in self.environments
        ]
        metrics = self._aggregate_terminal(per_site, update_state=False)
        
        # 3. Calculate BPE bonus and triangle penalties
        reused_bpe_modules, bpe_bonus = _reused_bpe_module_summary(layout_graphs, episode=self.episode)
            
        # Count post-merge triangles using actual polygon geometry (same logic as _finish_episode)
        post_merge_triangles = graph.count_post_merge_triangles(layout_graphs)
        unmerged_triangles = len(post_merge_triangles)
        unmerged_triangle_penalty = _average_unmerged_triangle_penalty(
            unmerged_triangles, len(layout_graphs)
        )
        
        dict_limit = int(self.settings["dictCap"])
        prelim_vocab_size = len(self.dictionary)
        dict_limit_breach = max(0, prelim_vocab_size - dict_limit)
        breach_multiplier = 5.0 + 15.0 * min(1.0, float(self.episode) / 100.0)
        dict_breach_penalty = min(80.0, float(dict_limit_breach ** 2) * breach_multiplier)

        frontier_metrics = self._relative_frontier_reward(update_state=False)
        score = (
            float(metrics["score"])
            + bpe_bonus
            - unmerged_triangle_penalty
            + float(frontier_metrics["relativeTimeReward"])
            - dict_breach_penalty
        )
        metrics["score"] = f"{score:.4f}"
        metrics["dictBreachPenalty"] = dict_breach_penalty
        metrics["dictLimitBreach"] = dict_limit_breach
        metrics["vocabSize"] = bpe_stats["unique_types"]
        metrics["totalPlacements"] = bpe_stats["total_placements"]
        metrics["bpeRounds"] = bpe_stats["merge_rounds"]
        metrics["reusedBpeModules"] = reused_bpe_modules
        metrics["bpeBonus"] = bpe_bonus
        metrics["unmergedTriangles"] = unmerged_triangles
        metrics["averageUnmergedTriangles"] = unmerged_triangles / max(1, len(layout_graphs))
        metrics["unmergedTrianglePenalty"] = unmerged_triangle_penalty
        metrics.update(frontier_metrics)
        diagnostics = self._runtime_diagnostics()
        metrics["runtimeDiagnostics"] = diagnostics
        
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
            "coreStacking": self._core_stacking_event(),
            "diagnostics": diagnostics,
        }

    def save_checkpoint(self) -> str:
        """Persist the complete session policy state in a portable checkpoint."""

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        path = os.path.join(OUTPUT_DIR, "checkpoint.pt")
        cpu_state = {name: tensor.detach().cpu() for name, tensor in self.model.state_dict().items()}
        payload = {
            "version": 5,
            "model": cpu_state,
            "optimizer": self.optimizer.state_dict(),
            "settings": dict(self.settings),
            "generationId": self.generation_id,
            "episode": self.episode,
            "baseline": self.baseline,
            "scoreHistory": list(self.score_history),
            "bestScore": self.best_score,
            "topologyMultiplier": self.topology_multiplier,
            "rewardState": self._checkpoint_reward_state(),
            "torchRngState": _capture_torch_rng_state(),
            "learnerTelemetry": {
                "policyLoss": self.last_loss,
                "actorLoss": self.last_actor_loss,
                "valueLoss": self.last_value_loss,
                "policyEntropy": self.last_entropy,
                "gradientNorm": self.last_gradient_norm,
                "advantage": self.last_advantage,
            },
        }
        temporary = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
        try:
            torch.save(payload, temporary)
            os.replace(temporary, path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
        return path

    def load_checkpoint_data(self, data_bytes: bytes) -> dict[str, Any]:
        """Load session policy state from checkpoint binary data, and commit it."""
        import io

        if not isinstance(data_bytes, (bytes, bytearray)) or not data_bytes:
            raise ValueError("checkpoint data must be non-empty bytes")
        if len(data_bytes) > MAX_CHECKPOINT_BYTES:
            raise ValueError("checkpoint exceeds the 64 MiB safety limit")
        if not _safe_checkpoint_loading_supported():
            raise RuntimeError(
                "checkpoint loading requires PyTorch 2.6 or newer because "
                "older weights-only loaders are affected by CVE-2025-32434"
            )
        checkpoint = torch.load(
            io.BytesIO(data_bytes), map_location="cpu", weights_only=True
        )
        if not isinstance(checkpoint, dict):
            raise ValueError("checkpoint root must be an object")
        for required_key in ("model", "optimizer"):
            if not isinstance(checkpoint.get(required_key), dict):
                raise ValueError(f"checkpoint {required_key} state is invalid")
        
        # Keep old states in case load fails
        old_model_state = {
            name: tensor.detach().clone() for name, tensor in self.model.state_dict().items()
        }
        old_optimizer = self.optimizer
        old_optimizer_state = copy.deepcopy(self.optimizer.state_dict())
        old_settings = self.settings
        old_generation_id = self.generation_id
        old_episode = self.episode
        old_baseline = self.baseline
        old_score_history = self.score_history
        old_best_score = self.best_score
        old_topology_multiplier = self.topology_multiplier
        old_reward_state = self._checkpoint_reward_state()
        old_rng_state = _capture_torch_rng_state()
        old_generation_state = (
            self.environments,
            self.dictionary,
            self.shape_log_probs,
            self.building_shape_log_probs,
            self.placement_log_probs,
            self.core_stack_records,
            self.core_stacking_metadata,
            self._prepared_initial_core_stacks,
            self.placement_log_probs_by_environment,
            self.placement_decisions,
            self.step_number,
            copy.deepcopy(self.step_profiler._samples),
            self.episode_generation_seconds,
            self.episode_action_normalized_seconds,
            self.episode_candidate_evaluations,
            self.episode_frontier_growth,
            self.episode_frontier_samples,
        )
        old_learner_telemetry = (
            self.last_loss,
            self.last_actor_loss,
            self.last_value_loss,
            self.last_entropy,
            self.last_gradient_norm,
            self.last_advantage,
        )
        
        try:
            checkpoint_version = int(checkpoint.get("version", 1))
            if checkpoint_version < 1 or checkpoint_version > 5:
                raise ValueError(f"unsupported checkpoint version: {checkpoint_version}")
            if checkpoint_version >= 5 and (
                not isinstance(checkpoint.get("rewardState"), dict)
                or not isinstance(checkpoint.get("torchRngState"), dict)
            ):
                raise ValueError("version-5 checkpoint is missing resumable state")

            def finite_scalar(key: str, default: float) -> float:
                value = float(checkpoint.get(key, default))
                if not math.isfinite(value):
                    raise ValueError(f"checkpoint {key} is not finite")
                return value

            def nonnegative_integer(key: str, default: int) -> int:
                raw = checkpoint.get(key, default)
                if type(raw) is not int or raw < 0 or raw > 2**31 - 1:
                    raise ValueError(f"checkpoint {key} is invalid")
                return raw

            generation_id = nonnegative_integer("generationId", 0)
            episode = nonnegative_integer("episode", 0)
            baseline = finite_scalar("baseline", 0.35)
            best_score = finite_scalar("bestScore", 0.0)
            topology_multiplier = finite_scalar("topologyMultiplier", 0.08)
            if not 0.0 <= topology_multiplier <= 1.0:
                raise ValueError("checkpoint topologyMultiplier is out of range")
            raw_score_history = checkpoint.get("scoreHistory", [])
            if not isinstance(raw_score_history, (list, tuple)) or len(raw_score_history) > 10000:
                raise ValueError("checkpoint scoreHistory is invalid")
            score_history = [float(value) for value in raw_score_history]
            if not all(math.isfinite(value) for value in score_history):
                raise ValueError("checkpoint scoreHistory is not finite")
            learner_telemetry = checkpoint.get("learnerTelemetry", {})
            if not isinstance(learner_telemetry, dict):
                raise ValueError("checkpoint learnerTelemetry is invalid")
            telemetry_values = {
                key: float(learner_telemetry.get(key, 0.0))
                for key in (
                    "policyLoss",
                    "actorLoss",
                    "valueLoss",
                    "policyEntropy",
                    "gradientNorm",
                    "advantage",
                )
            }
            if not all(math.isfinite(value) for value in telemetry_values.values()):
                raise ValueError("checkpoint learner telemetry is not finite")

            def validate_safe_state(value: Any, path: str) -> None:
                if isinstance(value, torch.Tensor):
                    if value.is_floating_point() or value.is_complex():
                        if not bool(torch.isfinite(value).all()):
                            raise ValueError(f"checkpoint {path} contains non-finite tensors")
                    return
                if isinstance(value, dict):
                    for child_key, child in value.items():
                        if not isinstance(child_key, (str, int)):
                            raise ValueError(f"checkpoint {path} has an invalid key")
                        validate_safe_state(child, f"{path}.{child_key}")
                    return
                if isinstance(value, (list, tuple)):
                    for index, child in enumerate(value):
                        validate_safe_state(child, f"{path}[{index}]")
                    return
                if value is None or isinstance(value, (str, bool, int)):
                    return
                if isinstance(value, float) and math.isfinite(value):
                    return
                raise ValueError(f"checkpoint {path} contains an invalid value")

            if not checkpoint["model"] or not all(
                isinstance(name, str) and isinstance(value, torch.Tensor)
                for name, value in checkpoint["model"].items()
            ):
                raise ValueError("checkpoint model state is invalid")
            validate_safe_state(checkpoint["model"], "model")
            validate_safe_state(checkpoint["optimizer"], "optimizer")
            if checkpoint_version < 4:
                self.model.reset_value_head()
            load_result = self.model.load_state_dict(
                checkpoint["model"], strict=checkpoint_version >= 4
            )
            if checkpoint_version < 4:
                unexpected = list(load_result.unexpected_keys)
                unsupported_missing = [
                    key for key in load_result.missing_keys if not key.startswith("value_head.")
                ]
                if unexpected or unsupported_missing:
                    raise RuntimeError(
                        "legacy checkpoint has incompatible policy parameters: "
                        f"missing={unsupported_missing}, unexpected={unexpected}"
                    )
            self.settings = _validated_checkpoint_settings(
                checkpoint.get("settings", {}), checkpoint_version
            )
            try:
                self.optimizer.load_state_dict(checkpoint["optimizer"])
                _validate_adam_state_shapes(
                    self.optimizer, float(self.settings["learningRate"])
                )
            except (KeyError, TypeError, ValueError, RuntimeError):
                if checkpoint_version >= 4:
                    raise
                # v3 and older checkpoints predate the value head, so their
                # Adam parameter groups cannot include the new critic state.
                self.optimizer = optim.Adam(
                    self.model.parameters(), lr=float(self.settings["learningRate"])
                )
            self.generation_id = generation_id
            self.episode = episode
            self.baseline = baseline
            self.score_history = score_history
            self.best_score = best_score
            self.topology_multiplier = topology_multiplier
            self._restore_checkpoint_reward_state(checkpoint.get("rewardState"))
            if checkpoint_version >= 5:
                _restore_torch_rng_state(checkpoint.get("torchRngState"), self.device)
            self.last_loss = telemetry_values["policyLoss"]
            self.last_actor_loss = telemetry_values["actorLoss"]
            self.last_value_loss = telemetry_values["valueLoss"]
            self.last_entropy = telemetry_values["policyEntropy"]
            self.last_gradient_norm = telemetry_values["gradientNorm"]
            self.last_advantage = telemetry_values["advantage"]
            
            # Prepare new generation using the loaded policy/settings
            generation = self.generation_id + 1
            prepared = self._prepare_generation(
                self.settings, generation, self.episode
            )
            self._commit_generation(self.settings, generation, *prepared)
            event = self.site_event()
        except Exception:
            # Restore original state if anything failed
            self.model.load_state_dict(old_model_state)
            self.optimizer = old_optimizer
            self.optimizer.load_state_dict(old_optimizer_state)
            self.settings = old_settings
            self.generation_id = old_generation_id
            self.episode = old_episode
            self.baseline = old_baseline
            self.score_history = old_score_history
            self.best_score = old_best_score
            self.topology_multiplier = old_topology_multiplier
            self._restore_checkpoint_reward_state(old_reward_state)
            _restore_torch_rng_state(old_rng_state, self.device)
            (
                self.environments,
                self.dictionary,
                self.shape_log_probs,
                self.building_shape_log_probs,
                self.placement_log_probs,
                self.core_stack_records,
                self.core_stacking_metadata,
                self._prepared_initial_core_stacks,
                self.placement_log_probs_by_environment,
                self.placement_decisions,
                self.step_number,
                self.step_profiler._samples,
                self.episode_generation_seconds,
                self.episode_action_normalized_seconds,
                self.episode_candidate_evaluations,
                self.episode_frontier_growth,
                self.episode_frontier_samples,
            ) = old_generation_state
            (
                self.last_loss,
                self.last_actor_loss,
                self.last_value_loss,
                self.last_entropy,
                self.last_gradient_norm,
                self.last_advantage,
            ) = old_learner_telemetry
            raise
        return event



app = FastAPI(title="Module Lab v0.8.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def get_index() -> FileResponse:
    return FileResponse(os.path.join(PUBLIC_DIR, "index.html"))


@app.get("/app.js")
async def get_app_js() -> FileResponse:
    return FileResponse(os.path.join(PUBLIC_DIR, "app.js"))


@app.get("/styles.css")
async def get_styles_css() -> FileResponse:
    return FileResponse(os.path.join(PUBLIC_DIR, "styles.css"))


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


def _allowed_websocket_origin(origin: str | None) -> bool:
    """Allow non-browser clients and browser sessions served from localhost."""

    if origin is None:
        return True
    try:
        parsed = urlparse(origin)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and parsed.hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Serve one isolated trainer; heavy mutations run outside the event loop."""

    if not _allowed_websocket_origin(websocket.headers.get("origin")):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    trainer = ParallelTrainer()
    print(f"WebSocket trainer connected on device: {trainer.device.type}")
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
                elif command == "setMode":
                    mode_str = str(message.get("mode", "training"))
                    ack = await asyncio.to_thread(trainer.set_mode, mode_str)
                    await _send_json(websocket, ack)
                elif command == "loadCheckpoint":
                    import base64
                    file_data = message.get("fileData")
                    if not isinstance(file_data, str) or not file_data:
                        raise ValueError("No fileData provided in loadCheckpoint command")
                    if len(file_data) > ((MAX_CHECKPOINT_BYTES + 2) // 3) * 4:
                        raise ValueError("Checkpoint exceeds the 64 MiB safety limit")
                    data_bytes = base64.b64decode(file_data, validate=True)
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
            except CoreStackingError as error:
                await _send_json(
                    websocket,
                    _error_event(
                        trainer,
                        str(error),
                        command=command,
                        code="core_stacking_error",
                        recoverable=True,
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
    print(f"Module Lab v0.8.0 policy device: {select_device().type}")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="127.0.0.1", port=port)
