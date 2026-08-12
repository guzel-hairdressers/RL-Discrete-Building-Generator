#!/usr/bin/env python3
"""Reproducible end-to-end benchmark for Module Lab trainer variants.

The controller never imports a project ``server`` module.  Every
``[label=]--module-dir``/seed pair is measured in a fresh child interpreter,
which makes before/after comparisons immune to ``sys.modules`` contamination
and native-library path reuse.

The normal benchmark sizes are 10 and 20 measured episodes.  Smaller positive
values are intentionally accepted for CI and smoke tests.
"""

from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import platform
import random
import resource
import statistics
import subprocess
import sys
import time
import traceback
import tracemalloc
from typing import Any, Iterable, Sequence


SCHEMA_VERSION = 1
WORKER_SENTINEL = "MODULE_LAB_BENCHMARK_RESULT="
SCRIPT_PATH = Path(__file__).resolve()
DEFAULT_MODULE_DIR = SCRIPT_PATH.parents[1]


class BenchmarkLimitError(RuntimeError):
    """Raised when an episode exceeds a configured safety limit."""


def percentile(values: Sequence[float], quantile: float) -> float | None:
    """Return a linearly interpolated percentile without third-party packages."""

    finite = sorted(float(value) for value in values if math.isfinite(float(value)))
    if not finite:
        return None
    if len(finite) == 1:
        return finite[0]
    position = min(1.0, max(0.0, float(quantile))) * (len(finite) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return finite[lower]
    fraction = position - lower
    return finite[lower] * (1.0 - fraction) + finite[upper] * fraction


def numeric_summary(values: Iterable[Any]) -> dict[str, float | int | None]:
    finite: list[float] = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            finite.append(number)
    if not finite:
        return {
            "count": 0,
            "mean": None,
            "min": None,
            "max": None,
            "p50": None,
            "p95": None,
            "stdev": None,
        }
    return {
        "count": len(finite),
        "mean": statistics.fmean(finite),
        "min": min(finite),
        "max": max(finite),
        "p50": percentile(finite, 0.50),
        "p95": percentile(finite, 0.95),
        "stdev": statistics.pstdev(finite) if len(finite) > 1 else 0.0,
    }


def _round_number(value: Any, digits: int = 7) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        number = float(value)
        if math.isfinite(number):
            return round(number, digits)
        return str(number)
    return value


def stable_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def polygon_signature(poly: Any) -> str | None:
    """Return a translation/rotation/cyclic-start invariant polygon signature."""

    if not isinstance(poly, list) or len(poly) < 3:
        return None
    edges: list[tuple[float, float, float]] = []
    try:
        for index, point in enumerate(poly):
            other = poly[(index + 1) % len(poly)]
            dx = float(other["x"]) - float(point["x"])
            dy = float(other["y"]) - float(point["y"])
            length = math.hypot(dx, dy)
            if length <= 1.0e-12:
                return None
            edges.append((dx, dy, length))
    except (KeyError, TypeError, ValueError):
        return None

    features: list[tuple[float, float, float]] = []
    for index, (dx, dy, length) in enumerate(edges):
        next_dx, next_dy, next_length = edges[(index + 1) % len(edges)]
        scale = length * next_length
        features.append(
            (
                round(length, 6),
                round((dx * next_dx + dy * next_dy) / scale, 7),
                round((dx * next_dy - dy * next_dx) / scale, 7),
            )
        )
    rotations = [tuple(features[offset:] + features[:offset]) for offset in range(len(features))]
    return stable_hash(min(rotations))


def _stable_polygon(poly: Any) -> list[dict[str, float]]:
    if not isinstance(poly, list):
        return []
    points: list[tuple[float, float]] = []
    for point in poly:
        if not isinstance(point, dict):
            continue
        try:
            x = float(point["x"])
            y = float(point["y"])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(x) and math.isfinite(y):
            points.append((round(x, 7), round(y, 7)))
    if len(points) > 1 and points[0] == points[-1]:
        points.pop()
    if not points:
        return []
    # Equivalent polygon encodings may choose a different first vertex or
    # winding. Canonicalizing both keeps regression hashes geometry-based.
    variants = []
    for sequence in (points, list(reversed(points))):
        variants.extend(
            tuple(sequence[offset:] + sequence[:offset])
            for offset in range(len(sequence))
        )
    canonical = min(variants)
    return [{"x": x, "y": y} for x, y in canonical]


def _module_record(module: Any) -> dict[str, Any]:
    if not isinstance(module, dict):
        return {}
    return {
        "id": str(module.get("id", "")),
        "category": str(module.get("category", "")),
        "family": str(module.get("family", "")),
        "triangle": bool(module.get("triangle", False)),
        "polySignature": polygon_signature(module.get("poly")),
    }


def _placement_record(placement: Any) -> dict[str, Any]:
    if not isinstance(placement, dict):
        return {}
    module = placement.get("module", {})
    if not isinstance(module, dict):
        module = {}
    return {
        "id": str(placement.get("id", "")),
        "instanceIdx": int(placement.get("instanceIdx", -1)),
        "moduleId": str(module.get("id", placement.get("moduleId", ""))),
        "category": str(module.get("category", placement.get("category", ""))),
        "family": str(module.get("family", placement.get("family", ""))),
        "rotation": _round_number(placement.get("rotation", 0.0)),
        "area": _round_number(placement.get("area")),
        "neighbors": sorted(str(item) for item in placement.get("neighbors", []) or []),
        "poly": _stable_polygon(placement.get("poly")),
    }


def observable_action_record(event: dict[str, Any]) -> dict[str, Any]:
    """Capture only deterministic, externally observable action information."""

    placements = [_placement_record(item) for item in event.get("placements", [])]
    placements.sort(key=lambda item: (item["instanceIdx"], item["id"], item["moduleId"]))
    dictionary = [_module_record(item) for item in event.get("dictionary", [])]
    dictionary.sort(key=lambda item: item["id"])
    stack = event.get("stackDecision")
    stack_record = None
    if isinstance(stack, dict):
        stack_record = {
            key: _round_number(stack.get(key))
            for key in (
                "moduleId",
                "rotation",
                "localAnchor",
                "decisionScope",
                "floorCount",
                "policyCandidateCount",
                "noStackAvailable",
            )
            if key in stack
        }
    return {
        "step": int(event.get("step", 0)),
        "placements": placements,
        "dictionary": dictionary,
        "stackDecision": stack_record,
    }


def layout_hash(placements: Any) -> str:
    records = [_placement_record(item) for item in placements or []]
    records.sort(key=lambda item: (item["instanceIdx"], item["id"], item["moduleId"]))
    return stable_hash(records)


def dictionary_hash(dictionary: Any) -> str:
    records = [_module_record(item) for item in dictionary or []]
    records.sort(key=lambda item: item["id"])
    return stable_hash(records)


def parse_settings(source: str | None, overrides: Sequence[str]) -> dict[str, Any]:
    if not source:
        settings: Any = {}
    else:
        text = source
        if source.startswith("@"):
            text = Path(source[1:]).expanduser().read_text(encoding="utf-8")
        elif not source.lstrip().startswith(("{", "[")):
            candidate = Path(source).expanduser()
            try:
                if candidate.is_file():
                    text = candidate.read_text(encoding="utf-8")
            except OSError:
                # A very long inline value may not be representable as a path.
                # Let json.loads below produce the useful validation error.
                pass
        settings = json.loads(text)
    if not isinstance(settings, dict):
        raise ValueError("settings must decode to a JSON object")
    result = dict(settings)
    for override in overrides:
        if "=" not in override:
            raise ValueError(f"--set expects KEY=JSON, got {override!r}")
        key, raw_value = override.split("=", 1)
        if not key:
            raise ValueError("--set key cannot be empty")
        result[key] = json.loads(raw_value)
    return result


def parse_seeds(items: Sequence[str]) -> list[int]:
    seeds: list[int] = []
    for item in items:
        for part in item.split(","):
            part = part.strip()
            if not part:
                continue
            seed = int(part)
            if seed < 0 or seed > 2**31 - 1:
                raise ValueError(f"seed out of range: {seed}")
            seeds.append(seed)
    return seeds or [123]


def parse_module_spec(value: str, index: int) -> tuple[str, Path]:
    label = ""
    path_text = value
    if "=" in value:
        candidate_label, candidate_path = value.split("=", 1)
        if candidate_label and candidate_path:
            label, path_text = candidate_label, candidate_path
    path = Path(path_text).expanduser().resolve()
    if not label:
        label = path.name or f"module-{index + 1}"
    return label, path


def current_rss_bytes() -> int:
    statm = Path("/proc/self/statm")
    if statm.is_file():
        try:
            resident_pages = int(statm.read_text(encoding="ascii").split()[1])
            return resident_pages * int(os.sysconf("SC_PAGE_SIZE"))
        except (IndexError, OSError, ValueError):
            pass
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    scale = 1 if sys.platform == "darwin" else 1024
    return int(usage * scale)


def peak_rss_bytes() -> int:
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    scale = 1 if sys.platform == "darwin" else 1024
    return int(usage * scale)


def synchronize_torch(torch_module: Any, device: Any) -> None:
    device_type = str(getattr(device, "type", device))
    if device_type == "cuda":
        cuda = getattr(torch_module, "cuda", None)
        if cuda is not None and callable(getattr(cuda, "synchronize", None)):
            cuda.synchronize(device)
    elif device_type == "mps":
        mps = getattr(torch_module, "mps", None)
        if mps is not None and callable(getattr(mps, "synchronize", None)):
            mps.synchronize()


def reset_accelerator_peaks(torch_module: Any, device: Any) -> None:
    if str(getattr(device, "type", device)) != "cuda":
        return
    cuda = getattr(torch_module, "cuda", None)
    if cuda is not None and callable(getattr(cuda, "reset_peak_memory_stats", None)):
        cuda.reset_peak_memory_stats(device)


def accelerator_memory(torch_module: Any, device: Any) -> dict[str, int | None]:
    device_type = str(getattr(device, "type", device))
    if device_type == "cuda":
        cuda = getattr(torch_module, "cuda", None)
        if cuda is None:
            return {}
        result: dict[str, int | None] = {}
        for output_key, function_name in (
            ("allocatedBytes", "memory_allocated"),
            ("reservedBytes", "memory_reserved"),
            ("peakAllocatedBytes", "max_memory_allocated"),
            ("peakReservedBytes", "max_memory_reserved"),
        ):
            function = getattr(cuda, function_name, None)
            result[output_key] = int(function(device)) if callable(function) else None
        return result
    if device_type == "mps":
        mps = getattr(torch_module, "mps", None)
        if mps is None:
            return {}
        result = {}
        for output_key, function_name in (
            ("allocatedBytes", "current_allocated_memory"),
            ("driverAllocatedBytes", "driver_allocated_memory"),
        ):
            function = getattr(mps, function_name, None)
            try:
                result[output_key] = int(function()) if callable(function) else None
            except RuntimeError:
                result[output_key] = None
        return result
    return {}


def _update_memory_peak(peak: dict[str, int], sample: dict[str, int | None]) -> None:
    for key, value in sample.items():
        if isinstance(value, int):
            peak[key] = max(peak.get(key, value), value)


def _float_metric(metrics: dict[str, Any], key: str) -> float | None:
    try:
        value = float(metrics.get(key))
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _aggregate_profiler(
    target: dict[str, dict[str, float]], timings: Any
) -> None:
    if not isinstance(timings, dict):
        return
    for phase, sample in timings.items():
        if not isinstance(sample, dict):
            continue
        try:
            count = max(0.0, float(sample.get("count", 0.0)))
            average = float(sample.get("avg", 0.0))
            minimum = float(sample.get("min", average))
            maximum = float(sample.get("max", average))
        except (TypeError, ValueError):
            continue
        record = target.setdefault(
            str(phase),
            {"count": 0.0, "weightedTotalMs": 0.0, "minMs": minimum, "maxMs": maximum, "episodes": 0.0},
        )
        record["count"] += count
        record["weightedTotalMs"] += average * count
        record["minMs"] = min(record["minMs"], minimum)
        record["maxMs"] = max(record["maxMs"], maximum)
        record["episodes"] += 1.0


def _finalize_profiler(source: dict[str, dict[str, float]]) -> dict[str, dict[str, float | int | None]]:
    result = {}
    for phase, record in sorted(source.items()):
        count = record["count"]
        result[phase] = {
            "count": int(count),
            "meanMs": record["weightedTotalMs"] / count if count else None,
            "minMs": record["minMs"],
            "maxMs": record["maxMs"],
            "episodeCount": int(record["episodes"]),
        }
    return result


def _category_entropy(counts: dict[str, int]) -> float:
    total = sum(counts.values())
    if total <= 0:
        return 0.0
    return -sum(
        (count / total) * math.log(count / total)
        for count in counts.values()
        if count > 0
    )


def _run_episode(
    trainer: Any,
    torch_module: Any,
    max_steps: int,
    episode_timeout_seconds: float,
    collect_details: bool,
    memory_peak: dict[str, int],
) -> tuple[dict[str, Any], list[float], list[float], list[dict[str, Any]], float, int]:
    generation_id = trainer.generation_id
    episode = trainer.episode
    synchronize_torch(torch_module, trainer.device)
    episode_started = time.perf_counter()
    call_durations: list[float] = []
    action_step_durations: list[float] = []
    observable_actions: list[dict[str, Any]] = []
    calls = 0
    while True:
        elapsed = time.perf_counter() - episode_started
        if elapsed > episode_timeout_seconds:
            raise BenchmarkLimitError(
                f"episode {episode} exceeded {episode_timeout_seconds:g}s after {calls} calls"
            )
        if calls >= max_steps:
            raise BenchmarkLimitError(
                f"episode {episode} exceeded the {max_steps} step-call limit"
            )
        synchronize_torch(torch_module, trainer.device)
        step_started = time.perf_counter()
        event = trainer.step(generation_id, episode)
        synchronize_torch(torch_module, trainer.device)
        duration = time.perf_counter() - step_started
        calls += 1
        call_durations.append(duration)
        memory_peak["rssBytes"] = max(memory_peak.get("rssBytes", 0), current_rss_bytes())
        _update_memory_peak(memory_peak, accelerator_memory(torch_module, trainer.device))

        elapsed = time.perf_counter() - episode_started
        if elapsed > episode_timeout_seconds:
            raise BenchmarkLimitError(
                f"episode {episode} exceeded {episode_timeout_seconds:g}s after {calls} calls"
            )

        event_type = event.get("type") if isinstance(event, dict) else None
        if event_type == "episodeDone":
            return (
                event,
                call_durations,
                action_step_durations,
                observable_actions,
                time.perf_counter() - episode_started,
                calls,
            )
        action_step_durations.append(duration)
        if collect_details and isinstance(event, dict):
            observable_actions.append(observable_action_record(event))


def _episode_record(
    event: dict[str, Any],
    action_records: list[dict[str, Any]],
    episode_wall_seconds: float,
    call_durations: list[float],
    action_durations: list[float],
    call_count: int,
    measured_index: int,
) -> dict[str, Any]:
    metrics = event.get("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}
    placements = event.get("placements", [])
    dictionary = event.get("dictionary", [])
    topology_violations = metrics.get("topologyViolations", [])
    if not isinstance(topology_violations, list):
        topology_violations = []

    category_counts: dict[str, int] = {}
    placement_shape_signatures: set[str] = set()
    for placement in placements if isinstance(placements, list) else []:
        record = _placement_record(placement)
        category = record.get("category", "") or "unknown"
        category_counts[category] = category_counts.get(category, 0) + 1
        signature = polygon_signature(placement.get("poly") if isinstance(placement, dict) else None)
        if signature:
            placement_shape_signatures.add(signature)

    module_shape_signatures = sorted(
        signature
        for signature in (
            polygon_signature(item.get("poly"))
            for item in dictionary
            if isinstance(item, dict)
        )
        if signature
    )
    return {
        "measuredIndex": measured_index,
        "completedEpisode": event.get("completedEpisode"),
        "nextEpisode": event.get("nextEpisode"),
        "episodeWallSeconds": episode_wall_seconds,
        "stepCalls": call_count,
        "actionSteps": len(action_durations),
        "stepCallSeconds": numeric_summary(call_durations),
        "actionStepSeconds": numeric_summary(action_durations),
        "score": _float_metric(metrics, "score"),
        "rawScore": _float_metric(metrics, "rawScore"),
        "fillRatio": _float_metric(metrics, "fillRatio"),
        "rentableRatio": _float_metric(metrics, "rentableRatio"),
        "moduleCount": _float_metric(metrics, "moduleCount"),
        "dictionaryLength": _float_metric(metrics, "dictionaryLength"),
        "policyLoss": _float_metric(metrics, "policyLoss"),
        "baseline": _float_metric(metrics, "baseline"),
        "candidateEvaluations": _float_metric(metrics, "candidateEvaluations"),
        "topologyValid": metrics.get("topologyValid"),
        "topologyViolationRate": _float_metric(metrics, "topologyViolationRate"),
        "topologyPenalty": _float_metric(metrics, "topologyPenalty"),
        "topologyViolationCount": len(topology_violations),
        "bpeBonus": _float_metric(metrics, "bpeBonus"),
        "bpeRounds": _float_metric(metrics, "bpeRounds"),
        "reusedBpeModules": _float_metric(metrics, "reusedBpeModules"),
        "vocabSize": _float_metric(metrics, "vocabSize"),
        "unmergedTriangles": _float_metric(metrics, "unmergedTriangles"),
        "averageUnmergedTriangles": _float_metric(metrics, "averageUnmergedTriangles"),
        "unmergedTrianglePenalty": _float_metric(metrics, "unmergedTrianglePenalty"),
        "triangleRatio": _float_metric(metrics, "triangleRatio"),
        "layoutHash": layout_hash(placements),
        "actionHash": stable_hash(action_records),
        "dictionaryHash": dictionary_hash(dictionary),
        "placementShapeSignatures": sorted(placement_shape_signatures),
        "moduleShapeSignatures": module_shape_signatures,
        "categoryCounts": category_counts,
        "categoryEntropy": _category_entropy(category_counts),
        "profilerTimings": metrics.get("performanceTimings", {}),
    }


def _summarize_run(
    episodes: list[dict[str, Any]],
    total_wall_seconds: float,
    profiler: dict[str, dict[str, float]],
) -> dict[str, Any]:
    all_step_calls: list[float] = []
    all_action_steps: list[float] = []
    category_counts: dict[str, int] = {}
    placement_shapes: set[str] = set()
    module_shapes: set[str] = set()
    for episode in episodes:
        # Per-call samples are intentionally not retained in JSON. Reconstructing
        # global percentiles from per-episode quantiles would be wrong, so the
        # caller adds the exact aggregate timing summaries separately.
        for category, count in episode["categoryCounts"].items():
            category_counts[category] = category_counts.get(category, 0) + int(count)
        placement_shapes.update(episode["placementShapeSignatures"])
        module_shapes.update(episode["moduleShapeSignatures"])
    valid_topology = [item["topologyValid"] for item in episodes if isinstance(item["topologyValid"], bool)]
    return {
        "episodeWallSeconds": numeric_summary(item["episodeWallSeconds"] for item in episodes),
        "score": numeric_summary(item["score"] for item in episodes),
        "fillRatio": numeric_summary(item["fillRatio"] for item in episodes),
        "rentableRatio": numeric_summary(item["rentableRatio"] for item in episodes),
        "moduleCount": numeric_summary(item["moduleCount"] for item in episodes),
        "dictionaryLength": numeric_summary(item["dictionaryLength"] for item in episodes),
        "policyLoss": numeric_summary(item["policyLoss"] for item in episodes),
        "candidateEvaluations": numeric_summary(item["candidateEvaluations"] for item in episodes),
        "candidateEvaluationsTotal": sum(
            int(item["candidateEvaluations"] or 0) for item in episodes
        ),
        "topologyValidRate": (
            sum(valid_topology) / len(valid_topology) if valid_topology else None
        ),
        "topologyViolationRate": numeric_summary(item["topologyViolationRate"] for item in episodes),
        "topologyViolationCount": numeric_summary(
            item["topologyViolationCount"] for item in episodes
        ),
        "topologyPenalty": numeric_summary(item["topologyPenalty"] for item in episodes),
        "bpeBonus": numeric_summary(item["bpeBonus"] for item in episodes),
        "bpeRounds": numeric_summary(item["bpeRounds"] for item in episodes),
        "reusedBpeModules": numeric_summary(item["reusedBpeModules"] for item in episodes),
        "vocabSize": numeric_summary(item["vocabSize"] for item in episodes),
        "unmergedTriangles": numeric_summary(item["unmergedTriangles"] for item in episodes),
        "averageUnmergedTriangles": numeric_summary(
            item["averageUnmergedTriangles"] for item in episodes
        ),
        "unmergedTrianglePenalty": numeric_summary(
            item["unmergedTrianglePenalty"] for item in episodes
        ),
        "triangleRatio": numeric_summary(item["triangleRatio"] for item in episodes),
        "diversity": {
            "episodeCount": len(episodes),
            "uniqueLayoutHashes": len({item["layoutHash"] for item in episodes}),
            "uniqueActionHashes": len({item["actionHash"] for item in episodes}),
            "uniqueDictionaryHashes": len({item["dictionaryHash"] for item in episodes}),
            "uniquePlacementShapeSignatures": len(placement_shapes),
            "uniqueModuleShapeSignatures": len(module_shapes),
            "categoryCounts": category_counts,
            "categoryEntropy": _category_entropy(category_counts),
        },
        "profilerPhases": _finalize_profiler(profiler),
        "measuredWallSeconds": total_wall_seconds,
        "episodesPerSecond": len(episodes) / total_wall_seconds if total_wall_seconds > 0 else None,
        # Populated by the worker from exact per-call samples.
        "stepCallSeconds": numeric_summary(all_step_calls),
        "actionStepSeconds": numeric_summary(all_action_steps),
    }


def worker_main(payload: dict[str, Any]) -> dict[str, Any]:
    module_dir = Path(payload["moduleDir"]).resolve()
    src_dir = module_dir / "src" if (module_dir / "src" / "server.py").is_file() else module_dir
    for required in ("server.py", "geometry.py", "graph.py"):
        if not (src_dir / required).is_file():
            raise FileNotFoundError(f"{src_dir} is missing {required}")

    tracemalloc.start()
    process_rss_at_start = current_rss_bytes()
    seed = int(payload["seed"])
    random.seed(seed)
    sys.path.insert(0, str(src_dir))
    importlib.invalidate_caches()
    server = importlib.import_module("server")
    imported_server = Path(server.__file__).resolve()
    if imported_server != (src_dir / "server.py").resolve():
        raise RuntimeError(f"import contamination: loaded {imported_server}, expected {src_dir / 'server.py'}")
    torch_module = getattr(server, "torch")
    if callable(getattr(torch_module, "manual_seed", None)):
        torch_module.manual_seed(seed)
    cuda = getattr(torch_module, "cuda", None)
    if cuda is not None and callable(getattr(cuda, "manual_seed_all", None)):
        cuda.manual_seed_all(seed)

    settings = dict(payload["settings"])
    settings["seed"] = seed
    trainer = server.ParallelTrainer()
    profiler: dict[str, dict[str, float]] = {}
    all_step_call_durations: list[float] = []
    all_action_step_durations: list[float] = []
    episodes: list[dict[str, Any]] = []
    memory_peak: dict[str, int] = {"rssBytes": process_rss_at_start}
    try:
        trainer.update_settings(settings)
        synchronize_torch(torch_module, trainer.device)
        for _ in range(int(payload["warmupEpisodes"])):
            _run_episode(
                trainer,
                torch_module,
                int(payload["maxSteps"]),
                float(payload["episodeTimeoutSeconds"]),
                False,
                memory_peak,
            )

        gc.collect()
        synchronize_torch(torch_module, trainer.device)
        tracemalloc.reset_peak()
        reset_accelerator_peaks(torch_module, trainer.device)
        rss_at_measurement_start = current_rss_bytes()
        traced_at_start, _ = tracemalloc.get_traced_memory()
        accelerator_at_start = accelerator_memory(torch_module, trainer.device)
        memory_peak = {"rssBytes": rss_at_measurement_start}
        _update_memory_peak(memory_peak, accelerator_at_start)

        measured_started = time.perf_counter()
        for measured_index in range(int(payload["episodes"])):
            (
                event,
                call_durations,
                action_durations,
                action_records,
                episode_wall,
                call_count,
            ) = _run_episode(
                trainer,
                torch_module,
                int(payload["maxSteps"]),
                float(payload["episodeTimeoutSeconds"]),
                True,
                memory_peak,
            )
            record = _episode_record(
                event,
                action_records,
                episode_wall,
                call_durations,
                action_durations,
                call_count,
                measured_index,
            )
            episodes.append(record)
            all_step_call_durations.extend(call_durations)
            all_action_step_durations.extend(action_durations)
            _aggregate_profiler(profiler, record["profilerTimings"])
        synchronize_torch(torch_module, trainer.device)
        measured_wall = time.perf_counter() - measured_started
        traced_current, traced_peak = tracemalloc.get_traced_memory()
        accelerator_at_end = accelerator_memory(torch_module, trainer.device)
        _update_memory_peak(memory_peak, accelerator_at_end)
        rss_at_end = current_rss_bytes()
        memory_peak["rssBytes"] = max(memory_peak.get("rssBytes", 0), rss_at_end)

        summary = _summarize_run(episodes, measured_wall, profiler)
        summary["stepCallSeconds"] = numeric_summary(all_step_call_durations)
        summary["actionStepSeconds"] = numeric_summary(all_action_step_durations)
        return {
            "schemaVersion": SCHEMA_VERSION,
            "status": "complete",
            "label": payload["label"],
            "moduleDir": str(module_dir),
            "seed": seed,
            "settings": settings,
            "device": str(getattr(trainer.device, "type", trainer.device)),
            "pythonVersion": platform.python_version(),
            "torchVersion": str(getattr(torch_module, "__version__", "unknown")),
            "platform": platform.platform(),
            "warmupEpisodes": int(payload["warmupEpisodes"]),
            "episodesRequested": int(payload["episodes"]),
            "episodesCompleted": len(episodes),
            "learningObserved": all(item["policyLoss"] is not None for item in episodes),
            "determinism": {
                "actionSequenceHash": stable_hash([item["actionHash"] for item in episodes]),
                "layoutSequenceHash": stable_hash([item["layoutHash"] for item in episodes]),
                "dictionarySequenceHash": stable_hash(
                    [item["dictionaryHash"] for item in episodes]
                ),
            },
            "timing": {
                "measuredWallSeconds": measured_wall,
                "episodeWallSeconds": summary["episodeWallSeconds"],
                "stepCallSeconds": summary["stepCallSeconds"],
                "actionStepSeconds": summary["actionStepSeconds"],
                "episodesPerSecond": summary["episodesPerSecond"],
                "stepCalls": len(all_step_call_durations),
                "actionSteps": len(all_action_step_durations),
            },
            "memory": {
                "rssProcessStartBytes": process_rss_at_start,
                "rssMeasurementStartBytes": rss_at_measurement_start,
                "rssEndBytes": rss_at_end,
                "rssObservedPeakBytes": memory_peak.get("rssBytes"),
                "rssResourcePeakBytes": peak_rss_bytes(),
                "tracemallocStartBytes": traced_at_start,
                "tracemallocCurrentBytes": traced_current,
                "tracemallocPeakBytes": traced_peak,
                "tracemallocPeakGrowthBytes": max(0, traced_peak - traced_at_start),
                "acceleratorStart": accelerator_at_start,
                "acceleratorEnd": accelerator_at_end,
                "acceleratorObservedPeaks": {
                    key: value for key, value in memory_peak.items() if key != "rssBytes"
                },
            },
            "quality": {
                key: value
                for key, value in summary.items()
                if key
                in {
                    "score",
                    "fillRatio",
                    "rentableRatio",
                    "moduleCount",
                    "dictionaryLength",
                    "policyLoss",
                    "candidateEvaluations",
                    "candidateEvaluationsTotal",
                    "topologyValidRate",
                    "topologyViolationRate",
                    "topologyViolationCount",
                    "topologyPenalty",
                    "bpeBonus",
                    "bpeRounds",
                    "reusedBpeModules",
                    "vocabSize",
                    "unmergedTriangles",
                    "averageUnmergedTriangles",
                    "unmergedTrianglePenalty",
                    "triangleRatio",
                }
            },
            "diversity": summary["diversity"],
            "profilerPhases": summary["profilerPhases"],
            "episodes": episodes,
        }
    finally:
        executor = getattr(trainer, "executor", None)
        if executor is not None and callable(getattr(executor, "shutdown", None)):
            executor.shutdown(wait=True, cancel_futures=True)
        tracemalloc.stop()


def _worker_payload_result(payload_text: str) -> int:
    try:
        payload = json.loads(payload_text)
        result = worker_main(payload)
    except Exception as error:  # pragma: no cover - exercised through controller
        result = {
            "schemaVersion": SCHEMA_VERSION,
            "status": "error",
            "errorType": type(error).__name__,
            "error": str(error),
            "traceback": traceback.format_exc(),
        }
    print(WORKER_SENTINEL + json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


def _extract_worker_result(output: str) -> dict[str, Any]:
    for line in reversed(output.splitlines()):
        if line.startswith(WORKER_SENTINEL):
            return json.loads(line[len(WORKER_SENTINEL) :])
    raise RuntimeError(f"worker produced no result sentinel; output was:\n{output[-4000:]}")


def _run_worker(payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    command = [sys.executable, str(SCRIPT_PATH), "--_worker-payload", json.dumps(payload, separators=(",", ":"))]
    started = time.perf_counter()
    try:
        worker_environment = os.environ.copy()
        worker_environment["PYTHONHASHSEED"] = str(payload["seed"])
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout_seconds,
            check=False,
            env=worker_environment,
        )
    except subprocess.TimeoutExpired as error:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "status": "timeout",
            "label": payload["label"],
            "moduleDir": payload["moduleDir"],
            "seed": payload["seed"],
            "controllerWallSeconds": time.perf_counter() - started,
            "error": f"worker exceeded {timeout_seconds:g}s",
            "output": (error.stdout or "")[-4000:] if isinstance(error.stdout, str) else "",
        }
    try:
        result = _extract_worker_result(completed.stdout)
    except Exception as error:
        result = {
            "schemaVersion": SCHEMA_VERSION,
            "status": "error",
            "label": payload["label"],
            "moduleDir": payload["moduleDir"],
            "seed": payload["seed"],
            "error": str(error),
            "workerExitCode": completed.returncode,
            "output": completed.stdout[-4000:],
        }
    result.setdefault("label", payload["label"])
    result.setdefault("moduleDir", payload["moduleDir"])
    result.setdefault("seed", payload["seed"])
    result["controllerWallSeconds"] = time.perf_counter() - started
    result["workerExitCode"] = completed.returncode
    return result


def _aggregate_modules(runs: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for run in runs:
        if run.get("status") != "complete":
            continue
        grouped.setdefault((str(run["label"]), str(run["moduleDir"])), []).append(run)
    result = []
    for (label, module_dir), items in grouped.items():
        episodes = [episode for run in items for episode in run.get("episodes", [])]
        result.append(
            {
                "label": label,
                "moduleDir": module_dir,
                "runCount": len(items),
                "seedCount": len({run["seed"] for run in items}),
                "episodeCount": len(episodes),
                "episodeWallSeconds": numeric_summary(
                    episode.get("episodeWallSeconds") for episode in episodes
                ),
                "score": numeric_summary(episode.get("score") for episode in episodes),
                "fillRatio": numeric_summary(episode.get("fillRatio") for episode in episodes),
                "rentableRatio": numeric_summary(
                    episode.get("rentableRatio") for episode in episodes
                ),
                "uniqueLayoutHashes": len({episode.get("layoutHash") for episode in episodes}),
                "uniqueActionHashes": len({episode.get("actionHash") for episode in episodes}),
            }
        )
    return sorted(result, key=lambda item: item["label"])


def _comparisons(runs: Sequence[dict[str, Any]], labels: Sequence[str]) -> list[dict[str, Any]]:
    if len(labels) < 2:
        return []
    baseline_label = labels[0]
    baseline_runs = {
        int(run["seed"]): run
        for run in runs
        if run.get("status") == "complete" and run.get("label") == baseline_label
    }
    comparisons = []
    for contender_label in labels[1:]:
        pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for run in runs:
            if run.get("status") != "complete" or run.get("label") != contender_label:
                continue
            baseline = baseline_runs.get(int(run["seed"]))
            if baseline is None:
                continue
            by_index = {int(item["measuredIndex"]): item for item in baseline["episodes"]}
            for episode in run["episodes"]:
                prior = by_index.get(int(episode["measuredIndex"]))
                if prior is not None:
                    pairs.append((prior, episode))
        baseline_times = [pair[0]["episodeWallSeconds"] for pair in pairs]
        contender_times = [pair[1]["episodeWallSeconds"] for pair in pairs]
        baseline_mean = statistics.fmean(baseline_times) if baseline_times else None
        contender_mean = statistics.fmean(contender_times) if contender_times else None
        comparisons.append(
            {
                "baseline": baseline_label,
                "contender": contender_label,
                "pairedEpisodes": len(pairs),
                "actionHashMatches": sum(first["actionHash"] == second["actionHash"] for first, second in pairs),
                "layoutHashMatches": sum(first["layoutHash"] == second["layoutHash"] for first, second in pairs),
                "meanScoreDelta": (
                    statistics.fmean(
                        float(second["score"]) - float(first["score"])
                        for first, second in pairs
                        if first["score"] is not None and second["score"] is not None
                    )
                    if any(first["score"] is not None and second["score"] is not None for first, second in pairs)
                    else None
                ),
                "episodeWallSpeedup": (
                    baseline_mean / contender_mean
                    if baseline_mean is not None and contender_mean not in (None, 0.0)
                    else None
                ),
            }
        )
    return comparisons


def _episode_csv_rows(runs: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for run_index, run in enumerate(runs):
        for episode in run.get("episodes", []):
            rows.append(
                {
                    "runIndex": run_index,
                    "label": run.get("label"),
                    "moduleDir": run.get("moduleDir"),
                    "seed": run.get("seed"),
                    "device": run.get("device"),
                    "warmupEpisodes": run.get("warmupEpisodes"),
                    "measuredIndex": episode.get("measuredIndex"),
                    "completedEpisode": episode.get("completedEpisode"),
                    "episodeWallSeconds": episode.get("episodeWallSeconds"),
                    "stepCalls": episode.get("stepCalls"),
                    "actionSteps": episode.get("actionSteps"),
                    "stepP50Seconds": episode.get("stepCallSeconds", {}).get("p50"),
                    "stepP95Seconds": episode.get("stepCallSeconds", {}).get("p95"),
                    "score": episode.get("score"),
                    "rawScore": episode.get("rawScore"),
                    "fillRatio": episode.get("fillRatio"),
                    "rentableRatio": episode.get("rentableRatio"),
                    "moduleCount": episode.get("moduleCount"),
                    "dictionaryLength": episode.get("dictionaryLength"),
                    "policyLoss": episode.get("policyLoss"),
                    "candidateEvaluations": episode.get("candidateEvaluations"),
                    "topologyValid": episode.get("topologyValid"),
                    "topologyViolationRate": episode.get("topologyViolationRate"),
                    "topologyViolationCount": episode.get("topologyViolationCount"),
                    "topologyPenalty": episode.get("topologyPenalty"),
                    "bpeBonus": episode.get("bpeBonus"),
                    "bpeRounds": episode.get("bpeRounds"),
                    "reusedBpeModules": episode.get("reusedBpeModules"),
                    "vocabSize": episode.get("vocabSize"),
                    "unmergedTriangles": episode.get("unmergedTriangles"),
                    "averageUnmergedTriangles": episode.get("averageUnmergedTriangles"),
                    "unmergedTrianglePenalty": episode.get("unmergedTrianglePenalty"),
                    "triangleRatio": episode.get("triangleRatio"),
                    "categoryEntropy": episode.get("categoryEntropy"),
                    "layoutHash": episode.get("layoutHash"),
                    "actionHash": episode.get("actionHash"),
                    "dictionaryHash": episode.get("dictionaryHash"),
                    "categoryCountsJson": json.dumps(episode.get("categoryCounts", {}), sort_keys=True),
                    "profilerTimingsJson": json.dumps(episode.get("profilerTimings", {}), sort_keys=True),
                }
            )
    return rows


def _write_json(path: str, report: dict[str, Any]) -> None:
    output = Path(path).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: str, runs: Sequence[dict[str, Any]]) -> None:
    output = Path(path).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = _episode_csv_rows(runs)
    fieldnames = list(rows[0]) if rows else ["runIndex", "label", "moduleDir", "seed"]
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _print_summary(report: dict[str, Any]) -> None:
    print("Module Lab benchmark")
    for item in report["moduleSummaries"]:
        wall = item["episodeWallSeconds"]
        score = item["score"]
        print(
            f"  {item['label']}: episodes={item['episodeCount']} "
            f"wall mean={wall['mean']:.4f}s p50={wall['p50']:.4f}s p95={wall['p95']:.4f}s "
            f"score mean={score['mean']:.3f}"
            if wall["mean"] is not None and score["mean"] is not None
            else f"  {item['label']}: episodes={item['episodeCount']} (insufficient metrics)"
        )
    for run in report["runs"]:
        if run.get("status") != "complete":
            continue
        steps = run["timing"]["stepCallSeconds"]
        print(
            f"    {run['label']} seed={run['seed']} step "
            f"p50={steps['p50'] * 1000.0:.3f}ms p95={steps['p95'] * 1000.0:.3f}ms "
            f"calls={run['timing']['stepCalls']}"
        )
    for item in report["comparisons"]:
        speedup = item["episodeWallSpeedup"]
        print(
            f"  compare {item['baseline']} -> {item['contender']}: "
            f"speedup={speedup:.3f}x paired={item['pairedEpisodes']} "
            f"action-hash={item['actionHashMatches']} layout-hash={item['layoutHashMatches']}"
            if speedup is not None
            else f"  compare {item['baseline']} -> {item['contender']}: no paired timings"
        )
    failures = [run for run in report["runs"] if run.get("status") != "complete"]
    for run in failures:
        print(f"  FAILED {run.get('label')} seed={run.get('seed')}: {run.get('error', run.get('status'))}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--module-dir",
        action="append",
        default=[],
        metavar="[LABEL=]PATH",
        help="Project directory containing server.py; repeat for before/after comparison.",
    )
    parser.add_argument(
        "--episodes",
        type=int,
        default=10,
        help="Measured complete episodes per seed (normally 10 or 20; smaller values are for smoke tests).",
    )
    parser.add_argument("--warmup", type=int, default=0, help="Complete learning episodes before measurement.")
    parser.add_argument(
        "--seed",
        action="append",
        default=[],
        help="Seed or comma-separated seeds; repeat to add independent runs.",
    )
    parser.add_argument(
        "--settings",
        help="Settings JSON object, JSON file path, or @JSON_FILE. The run seed overrides its seed field.",
    )
    parser.add_argument(
        "--set",
        dest="setting_overrides",
        action="append",
        default=[],
        metavar="KEY=JSON",
        help="Override one setting after --settings; repeat as needed.",
    )
    parser.add_argument("--max-steps", type=int, default=2000, help="Maximum trainer.step calls per episode.")
    parser.add_argument(
        "--episode-timeout",
        type=float,
        default=300.0,
        help="Per-episode wall timeout in seconds.",
    )
    parser.add_argument(
        "--run-timeout",
        type=float,
        help="Controller timeout per module/seed worker. Defaults from episode limits.",
    )
    parser.add_argument("--json-out", help="Write the complete report as JSON.")
    parser.add_argument("--csv-out", help="Write one flattened row per measured episode as CSV.")
    parser.add_argument("--quiet", action="store_true", help="Suppress the human-readable summary.")
    parser.add_argument("--_worker-payload", help=argparse.SUPPRESS)
    return parser


def controller_main(args: argparse.Namespace) -> int:
    if args.episodes <= 0:
        raise ValueError("--episodes must be positive")
    if args.warmup < 0:
        raise ValueError("--warmup cannot be negative")
    if args.max_steps <= 0:
        raise ValueError("--max-steps must be positive")
    if args.episode_timeout <= 0:
        raise ValueError("--episode-timeout must be positive")
    if args.run_timeout is not None and args.run_timeout <= 0:
        raise ValueError("--run-timeout must be positive")

    settings = parse_settings(args.settings, args.setting_overrides)
    seeds = parse_seeds(args.seed)
    raw_modules = args.module_dir or [str(DEFAULT_MODULE_DIR)]
    modules = [parse_module_spec(value, index) for index, value in enumerate(raw_modules)]
    labels = [label for label, _ in modules]
    if len(set(labels)) != len(labels):
        raise ValueError("module labels must be unique; use LABEL=PATH")
    timeout_seconds = args.run_timeout or (
        args.episode_timeout * (args.episodes + args.warmup) + 60.0
    )

    runs = []
    report_started = time.perf_counter()
    for label, module_dir in modules:
        for seed in seeds:
            payload = {
                "label": label,
                "moduleDir": str(module_dir),
                "seed": seed,
                "settings": settings,
                "episodes": args.episodes,
                "warmupEpisodes": args.warmup,
                "maxSteps": args.max_steps,
                "episodeTimeoutSeconds": args.episode_timeout,
            }
            runs.append(_run_worker(payload, timeout_seconds))

    report = {
        "schemaVersion": SCHEMA_VERSION,
        "createdAtUnixSeconds": time.time(),
        "controllerPython": sys.version,
        "controllerPlatform": platform.platform(),
        "episodesPerSeed": args.episodes,
        "warmupEpisodes": args.warmup,
        "seeds": seeds,
        "settings": settings,
        "controllerWallSeconds": time.perf_counter() - report_started,
        "runs": runs,
        "moduleSummaries": _aggregate_modules(runs),
        "comparisons": _comparisons(runs, labels),
    }
    if args.json_out:
        _write_json(args.json_out, report)
    if args.csv_out:
        _write_csv(args.csv_out, runs)
    if not args.quiet:
        _print_summary(report)
    return 0 if all(run.get("status") == "complete" for run in runs) else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args._worker_payload is not None:
        return _worker_payload_result(args._worker_payload)
    try:
        return controller_main(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
