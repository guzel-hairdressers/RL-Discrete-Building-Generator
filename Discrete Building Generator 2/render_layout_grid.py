#!/usr/bin/env python3
"""Render deterministic Module Lab episode polygons as a PNG contact sheet.

Run this script in a fresh interpreter for each variant.  The two release
folders intentionally use the same top-level Python module names, so importing
both into one process would contaminate ``sys.modules``.
"""

from __future__ import annotations

import argparse
import copy
import importlib
import json
import math
import os
import random
import sys
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageFont


CATEGORY_COLORS = {
    "core": "#dc745d",
    "corridor": "#e1ba57",
    "room": "#a9c5ae",
    "special": "#6e9c89",
}
INK = "#111712"
INK_SOFT = "#48534b"
PAPER = "#f5f2ea"
CANVAS = "#e9e6de"
SITE = "#fbfaf6"
MUTED = "#77837a"
ACCENT = "#c4db8b"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render actual generated floor polygons as a PNG grid."
    )
    parser.add_argument("--module-dir", required=True, type=Path)
    parser.add_argument("--variant", required=True, choices=("v0.8.0", "v0.8.1"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--episodes", type=int, default=3)
    parser.add_argument("--floors", type=int, default=4)
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--max-modules", type=int)
    parser.add_argument("--max-step-calls", type=int, default=1000)
    args = parser.parse_args()
    if not 1 <= args.episodes <= 8:
        parser.error("--episodes must be between 1 and 8")
    if not 1 <= args.floors <= 8:
        parser.error("--floors must be between 1 and 8")
    return args


def polygon_area(poly: Iterable[dict[str, Any]]) -> float:
    points = list(poly)
    return abs(
        math.fsum(
            float(point["x"]) * float(points[(index + 1) % len(points)]["y"])
            - float(points[(index + 1) % len(points)]["x"]) * float(point["y"])
            for index, point in enumerate(points)
        )
    ) * 0.5


def load_font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def finite_number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def generate(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    module_dir = args.module_dir.resolve()
    if not (module_dir / "server.py").is_file():
        raise FileNotFoundError(f"server.py not found in {module_dir}")

    os.environ["MODULE_LAB_DEVICE"] = "cpu"
    sys.path.insert(0, str(module_dir))
    torch = importlib.import_module("torch")
    server = importlib.import_module("server")

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    max_modules = args.max_modules
    if max_modules is None:
        max_modules = 130 if args.variant == "v0.8.0" else 20
    settings: dict[str, Any] = {
        "boundaryType": "lobed",
        "atriumPolicy": "agent",
        "parallelEnvironments": args.floors,
        "maxModules": max_modules,
        "dictCap": 10,
        "angleStep": 15.0,
        "seed": args.seed,
    }
    if args.variant == "v0.8.0":
        settings["singleFloor"] = False

    trainer = server.ParallelTrainer()
    results: list[dict[str, Any]] = []
    try:
        site_event = trainer.update_settings(settings)
        boundaries = copy.deepcopy(site_event["boundaries"])
        for _ in range(args.episodes):
            generation_id = trainer.generation_id
            episode = trainer.episode
            for call_index in range(1, args.max_step_calls + 1):
                event = trainer.step(generation_id, episode)
                if event.get("type") == "episodeDone":
                    results.append(
                        {
                            "episode": int(event["completedEpisode"]),
                            "stepCalls": call_index,
                            "boundaries": copy.deepcopy(boundaries),
                            "placements": copy.deepcopy(event.get("placements", [])),
                            "metrics": copy.deepcopy(event.get("metrics", {})),
                            "coreStacking": copy.deepcopy(event.get("coreStacking")),
                        }
                    )
                    break
            else:
                raise RuntimeError(
                    f"episode {episode} exceeded {args.max_step_calls} step calls"
                )
    finally:
        trainer.executor.shutdown(wait=True)

    metadata = {
        "schemaVersion": 1,
        "variant": args.variant,
        "moduleDir": str(module_dir),
        "seed": args.seed,
        "settings": settings,
        "rendering": {
            "individualPreBpePlacements": True,
            "coordinates": "world",
            "fixedSiteAcrossRows": True,
            "categoryColors": CATEGORY_COLORS,
        },
    }
    return metadata, results


def bounds_for(boundary: dict[str, Any]) -> tuple[float, float, float, float]:
    points = boundary.get("outer", [])
    xs = [float(point["x"]) for point in points]
    ys = [float(point["y"]) for point in points]
    if not xs or not ys:
        raise ValueError("boundary has no outer polygon")
    return min(xs), min(ys), max(xs), max(ys)


def draw_grid(
    metadata: dict[str, Any], results: list[dict[str, Any]], output: Path
) -> None:
    scale_factor = 2
    columns = int(metadata["settings"]["parallelEnvironments"])
    rows = len(results)
    width = 1800
    margin_x = 42
    gap_x = 18
    header_h = 138
    panel_h = 342
    gap_y = 22
    footer_h = 54
    height = header_h + rows * panel_h + max(0, rows - 1) * gap_y + footer_h
    panel_w = (width - 2 * margin_x - (columns - 1) * gap_x) / columns

    def sc(value: float) -> int:
        return int(round(value * scale_factor))

    image = Image.new("RGB", (sc(width), sc(height)), CANVAS)
    draw = ImageDraw.Draw(image)
    font_title = load_font(sc(31), bold=True)
    font_subtitle = load_font(sc(14))
    font_panel = load_font(sc(14), bold=True)
    font_small = load_font(sc(11))
    font_tiny = load_font(sc(10))
    font_badge = load_font(sc(9), bold=True)

    variant = str(metadata["variant"])
    mode = "Exact shared-core stacking" if variant == "v0.8.0" else "Independent-floor optimizer"
    draw.text(
        (sc(margin_x), sc(28)),
        f"Module Lab {variant}  ·  {mode}",
        fill=INK,
        font=font_title,
    )
    draw.text(
        (sc(margin_x), sc(73)),
        (
            f"Actual generated polygons  ·  seed {metadata['seed']}  ·  "
            f"first {rows} episodes  ·  {columns} irregular floors per episode"
        ),
        fill=INK_SOFT,
        font=font_subtitle,
    )

    legend_x = margin_x
    legend_y = 105
    for category in ("core", "room", "corridor", "special"):
        draw.rounded_rectangle(
            (sc(legend_x), sc(legend_y), sc(legend_x + 18), sc(legend_y + 13)),
            radius=sc(3),
            fill=CATEGORY_COLORS[category],
            outline=INK,
            width=sc(1),
        )
        draw.text(
            (sc(legend_x + 25), sc(legend_y - 2)),
            category,
            fill=INK_SOFT,
            font=font_small,
        )
        legend_x += 104
    draw.rectangle(
        (sc(legend_x), sc(legend_y), sc(legend_x + 18), sc(legend_y + 13)),
        fill=CANVAS,
        outline=INK,
        width=sc(1),
    )
    draw.text(
        (sc(legend_x + 25), sc(legend_y - 2)),
        "atrium / void",
        fill=INK_SOFT,
        font=font_small,
    )

    for row_index, result in enumerate(results):
        row_y = header_h + row_index * (panel_h + gap_y)
        metrics = result.get("metrics", {})
        score = finite_number(metrics.get("score"))
        topology = bool(metrics.get("topologyValid", False))
        for floor_index in range(columns):
            x0 = margin_x + floor_index * (panel_w + gap_x)
            y0 = row_y
            x1 = x0 + panel_w
            y1 = y0 + panel_h
            draw.rounded_rectangle(
                (sc(x0), sc(y0), sc(x1), sc(y1)),
                radius=sc(14),
                fill=PAPER,
                outline="#cfd3cb",
                width=sc(1),
            )

            title = f"Episode {result['episode']}  ·  Floor {floor_index + 1}"
            draw.text((sc(x0 + 16), sc(y0 + 13)), title, fill=INK, font=font_panel)
            if floor_index == 0:
                topology_text = "topology ✓" if topology else "topology !"
                summary = f"score {score:.2f}  ·  {topology_text}"
                summary_width = draw.textbbox((0, 0), summary, font=font_tiny)[2]
                draw.text(
                    (sc(x1 - 15) - summary_width, sc(y0 + 16)),
                    summary,
                    fill=INK_SOFT if topology else "#9f3e2e",
                    font=font_tiny,
                )

            boundary = next(
                item
                for item in result["boundaries"]
                if int(item["instanceIdx"]) == floor_index
            )
            placements = [
                item
                for item in result["placements"]
                if int(item.get("instanceIdx", -1)) == floor_index
            ]
            min_x, min_y, max_x, max_y = bounds_for(boundary)
            world_w = max(1e-9, max_x - min_x)
            world_h = max(1e-9, max_y - min_y)
            body_left = x0 + 17
            body_top = y0 + 48
            body_right = x1 - 17
            body_bottom = y1 - 40
            body_w = body_right - body_left
            body_h = body_bottom - body_top
            geometry_scale = min(body_w / world_w, body_h / world_h) * 0.94
            geometry_w = world_w * geometry_scale
            geometry_h = world_h * geometry_scale
            origin_x = body_left + (body_w - geometry_w) * 0.5
            origin_y = body_top + (body_h - geometry_h) * 0.5

            def project(poly: Iterable[dict[str, Any]]) -> list[tuple[int, int]]:
                return [
                    (
                        sc(origin_x + (float(point["x"]) - min_x) * geometry_scale),
                        sc(origin_y + (max_y - float(point["y"])) * geometry_scale),
                    )
                    for point in poly
                ]

            outer = project(boundary["outer"])
            draw.polygon(outer, fill=SITE)
            for placement in placements:
                category = placement.get("module", {}).get("category", "room")
                points = project(placement.get("poly", []))
                if len(points) < 3:
                    continue
                draw.polygon(
                    points,
                    fill=CATEGORY_COLORS.get(category, CATEGORY_COLORS["room"]),
                    outline="#2f3b33",
                    width=sc(1),
                )
                if placement.get("coreStackLocked"):
                    draw.line(points + [points[0]], fill="#fff7dc", width=sc(2), joint="curve")
                    draw.line(points + [points[0]], fill="#8f382d", width=sc(1), joint="curve")

            for hole in boundary.get("holes", []):
                hole_points = project(hole)
                draw.polygon(hole_points, fill=CANVAS, outline=INK, width=sc(2))
            draw.line(outer + [outer[0]], fill=INK, width=sc(3), joint="curve")

            module_count = len(placements)
            core_count = sum(
                placement.get("module", {}).get("category") == "core"
                for placement in placements
            )
            filled_area = math.fsum(
                polygon_area(placement.get("poly", [])) for placement in placements
            )
            fill_ratio = filled_area / max(1e-9, finite_number(boundary.get("exactArea"), 1.0))
            footer = (
                f"{module_count} modules  ·  {core_count} core"
                f"{'s' if core_count != 1 else ''}  ·  fill {fill_ratio:.0%}"
            )
            draw.text(
                (sc(x0 + 16), sc(y1 - 29)), footer, fill=MUTED, font=font_small
            )

            if variant == "v0.8.0" and any(
                placement.get("coreStackLocked") for placement in placements
            ):
                badge = "LOCKED STACK"
                badge_width = draw.textbbox((0, 0), badge, font=font_badge)[2]
                badge_x = sc(x1 - 14) - badge_width - sc(14)
                badge_y = sc(y1 - 31)
                draw.rounded_rectangle(
                    (
                        badge_x - sc(6),
                        badge_y - sc(2),
                        badge_x + badge_width + sc(6),
                        badge_y + sc(14),
                    ),
                    radius=sc(5),
                    fill="#f3df9b",
                )
                draw.text((badge_x, badge_y), badge, fill="#6f332b", font=font_badge)

    footer_y = height - footer_h + 17
    note = (
        "Individual pre-BPE modules are shown.  The black outline is the exact site; "
        "open interior polygons are atria."
    )
    draw.text((sc(margin_x), sc(footer_y)), note, fill=MUTED, font=font_small)

    output.parent.mkdir(parents=True, exist_ok=True)
    image = image.resize((width, height), Image.Resampling.LANCZOS)
    image.save(output, format="PNG", optimize=True)


def main() -> int:
    args = parse_args()
    metadata, results = generate(args)
    draw_grid(metadata, results, args.output)
    manifest = args.output.with_suffix(".json")
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps({**metadata, "episodes": results}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(args.output.resolve())
    print(manifest.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
