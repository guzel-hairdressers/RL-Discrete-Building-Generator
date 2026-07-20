"""
Batch Fetcher — Automated algorithm to fetch 200–500 real urban context sites
from OpenStreetMap across world cities.

Features:
  - Generates candidate sample points from city_targets.py
  - Fetches OSM building + road data via Overpass API
  - Applies quality rejection filters (min FAR, min buildings, etc.)
  - Stores accepted sites in the file-based database
  - Supports pause/resume via Ctrl+C with state persistence
  - Rate-limited to respect Overpass API limits

Usage:
    python batch_fetcher.py                  # Start or resume fetching
    python batch_fetcher.py --reset          # Start fresh (clear all state)
    python batch_fetcher.py --target 300     # Stop after 300 accepted sites
    python batch_fetcher.py --radius 150     # Use 150m context radius
    python batch_fetcher.py --spacing 200    # Sample points every 200m
    python batch_fetcher.py --dry-run        # Preview candidates without fetching

    Press Ctrl+C at any time to pause — state is saved automatically.
"""

import argparse
import json
import math
import os
import signal
import sys
import time
import random
import urllib.request
import urllib.parse
from datetime import datetime, timezone

import numpy as np

from city_targets import get_all_candidate_points
from geometry_3d import latlon_to_local_meters, compute_quick_metrics
from site_database import (
    add_site, load_fetch_state, save_fetch_state, clear_fetch_state, ensure_dirs
)


# ---------------------------------------------------------------------------
# Overpass API Configuration — Multi-mirror pool for max reliability
# ---------------------------------------------------------------------------

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.nchc.org.tw/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

# How long to wait between requests (seconds)
MIN_DELAY = 1.5
MAX_DELAY = 3.5

# On rate limit (429/503), switch endpoint instantly with minimal delay
BACKOFF_DELAY = 3.0

# ---------------------------------------------------------------------------
# Rejection Criteria — thresholds for accepting a site
# ---------------------------------------------------------------------------

MIN_BUILDINGS = 4           # At least 4 buildings in the context
MIN_FAR = 1.5               # Floor area ratio must be >= 1.5
MIN_MAX_HEIGHT = 12.0       # Tallest building must be >= 12m
MIN_GCR = 0.10              # Ground coverage ratio must be >= 10%
MAX_DEFAULT_HEIGHT_RATIO = 0.60  # No more than 60% of buildings without height data
MIN_SITE_AREA = 350.0       # Reject sites with parcel area < 350 m² completely


def compute_area_tier(area_m2):
    """
    Categorize site by area:
        S  : 350 <= area < 600 m²
        M  : 600 <= area < 1,200 m²
        L  : 1,200 <= area < 2,500 m²
        XL : area >= 2,500 m²
    """
    if area_m2 < 350.0:
        return "REJECT"
    elif area_m2 < 600.0:
        return "S"
    elif area_m2 < 1200.0:
        return "M"
    elif area_m2 < 2500.0:
        return "L"
    else:
        return "XL"

# ---------------------------------------------------------------------------
# Global stop flag for Ctrl+C
# ---------------------------------------------------------------------------

_stop_requested = False


def _signal_handler(signum, frame):
    global _stop_requested
    _stop_requested = True
    print("\n\n[Pause] Ctrl+C received — saving state and stopping after current site...")


signal.signal(signal.SIGINT, _signal_handler)


# ---------------------------------------------------------------------------
# Overpass API Fetching
# ---------------------------------------------------------------------------

def fetch_overpass(lat, lon, radius, default_height):
    """
    Query Overpass API for buildings and roads around (lat, lon).
    Returns parsed buildings + roads in local meter coordinates, or None on failure.
    """
    query = f"""
    [out:json][timeout:15];
    (
      way["building"](around:{radius},{lat},{lon});
      relation["building"](around:{radius},{lat},{lon});
      way["highway"](around:{radius},{lat},{lon});
    );
    out body;
    >;
    out skel qt;
    """

    encoded_data = urllib.parse.urlencode({'data': query}).encode('utf-8')
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
    }

    # Try each endpoint
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            req = urllib.request.Request(endpoint, data=encoded_data, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    parsed = _parse_response(data, lat, lon, default_height)
                    if parsed and len(parsed["buildings"]) > 0:
                        return parsed
        except Exception:
            continue

    return None


def _parse_response(data, ref_lat, ref_lon, default_height):
    """Parse Overpass JSON response into local-coordinate buildings and roads."""
    elements = data.get("elements", [])
    nodes = {}
    building_ways = []
    highway_ways = []

    for el in elements:
        if el["type"] == "node":
            nodes[el["id"]] = (el["lat"], el["lon"])
        elif el["type"] == "way" and "tags" in el:
            tags = el["tags"]
            if "building" in tags:
                building_ways.append(el)
            elif "highway" in tags:
                highway_ways.append(el)

    buildings = []
    for way in building_ways:
        way_nodes = way.get("nodes", [])
        if len(way_nodes) < 3:
            continue

        local_coords = []
        for nid in way_nodes:
            if nid in nodes:
                nlat, nlon = nodes[nid]
                x, y = latlon_to_local_meters(nlat, nlon, ref_lat, ref_lon)
                local_coords.append([round(x, 2), round(y, 2)])

        if len(local_coords) < 3:
            continue

        tags = way.get("tags", {})
        height, height_source = _extract_height(tags, default_height)

        coords_arr = np.array(local_coords)
        centroid = np.mean(coords_arr, axis=0).tolist()
        dist_to_center = math.hypot(centroid[0], centroid[1])

        # Extract rich OSM building classification tags
        b_type = tags.get("building", "yes")
        b_use = tags.get("building:use", tags.get("amenity", tags.get("shop", tags.get("office", b_type))))

        buildings.append({
            "id": way["id"],
            "name": tags.get("name", f"Building {way['id']}"),
            "vertices_2d": local_coords,
            "centroid": centroid,
            "dist_to_center": dist_to_center,
            "height": height,
            "height_source": height_source,
            "building_type": b_type,
            "building_use": b_use,
            "tags": tags,
        })

    roads = []
    for way in highway_ways:
        way_nodes = way.get("nodes", [])
        if len(way_nodes) < 2:
            continue

        road_coords = []
        for nid in way_nodes:
            if nid in nodes:
                nlat, nlon = nodes[nid]
                x, y = latlon_to_local_meters(nlat, nlon, ref_lat, ref_lon)
                road_coords.append([round(x, 2), round(y, 2)])

        if len(road_coords) < 2:
            continue

        tags = way.get("tags", {})
        h_type = tags.get("highway", "residential")

        # Exclude non-vehicular roads (sidewalks, footways, paths, steps, etc.)
        NON_VEHICULAR_HIGHWAYS = {
            "footway", "pedestrian", "steps", "path", "sidewalk", "cycleway",
            "bridleway", "corridor", "proposed", "construction", "platform",
            "track", "footpath"
        }
        if h_type in NON_VEHICULAR_HIGHWAYS:
            continue

        roads.append({
            "id": way["id"],
            "name": tags.get("name", f"Road ({h_type})"),
            "highway_type": h_type,
            "polyline_2d": road_coords,
        })

    return {"buildings": buildings, "roads": roads}


def _extract_height(tags, default_height):
    """
    Extract building height from OSM tags.
    Returns (height_float, source_string).
    source is 'tag_height', 'tag_levels', or 'default'.
    """
    if "height" in tags:
        try:
            val = tags["height"].replace("m", "").replace("'", "").strip()
            return float(val), "tag_height"
        except (ValueError, AttributeError):
            pass
    if "building:height" in tags:
        try:
            val = tags["building:height"].replace("m", "").strip()
            return float(val), "tag_height"
        except (ValueError, AttributeError):
            pass
    if "building:levels" in tags:
        try:
            levels = float(tags["building:levels"])
            return max(4.0, levels * 3.5), "tag_levels"
        except (ValueError, AttributeError):
            pass

    return default_height, "default"


# ---------------------------------------------------------------------------
# Quality Filter
# ---------------------------------------------------------------------------

def evaluate_site(buildings, radius):
    """
    Evaluate whether a set of buildings constitutes a valid urban context site.

    Returns:
        (accepted: bool, reason: str, metrics: dict)
    """
    if len(buildings) < MIN_BUILDINGS:
        return False, f"too few buildings ({len(buildings)} < {MIN_BUILDINGS})", {}

    metrics = compute_quick_metrics(buildings, radius_m=radius)

    if metrics["far"] < MIN_FAR:
        return False, f"FAR too low ({metrics['far']} < {MIN_FAR})", metrics

    if metrics["max_height"] < MIN_MAX_HEIGHT:
        return False, f"max height too low ({metrics['max_height']}m < {MIN_MAX_HEIGHT}m)", metrics

    if metrics["gcr"] < MIN_GCR:
        return False, f"GCR too low ({metrics['gcr']} < {MIN_GCR})", metrics

    # Check how many buildings fell back to default height
    default_count = sum(1 for b in buildings if b.get("height_source") == "default")
    default_ratio = default_count / len(buildings)
    if default_ratio > MAX_DEFAULT_HEIGHT_RATIO:
        return False, f"too many default heights ({default_ratio:.0%} > {MAX_DEFAULT_HEIGHT_RATIO:.0%})", metrics

    return True, "accepted", metrics


# ---------------------------------------------------------------------------
# Main Batch Fetch Loop
# ---------------------------------------------------------------------------

def run_batch_fetch(target_count=500, radius=100.0, spacing=250.0, reset=False):
    """
    Main entry point. Fetches urban context sites in a loop with pause/resume support.
    """
    global _stop_requested
    ensure_dirs()

    # Generate all candidate points
    candidates = get_all_candidate_points(spacing_m=spacing)
    random.seed(42)
    random.shuffle(candidates)  # Shuffle so we don't hit the same city repeatedly

    total_candidates = len(candidates)
    print(f"{'=' * 70}")
    print(f"  URBAN CONTEXT DATABASE — BATCH FETCHER")
    print(f"{'=' * 70}")
    print(f"  Total candidate points : {total_candidates}")
    print(f"  Target accepted sites  : {target_count}")
    print(f"  Context radius         : {radius}m")
    print(f"  Sampling spacing       : {spacing}m")
    print(f"{'=' * 70}")

    # Load or initialize state
    if reset:
        clear_fetch_state()
        state = None
    else:
        state = load_fetch_state()

    if state and state.get("status") == "paused":
        start_index = state["current_index"]
        accepted = state["accepted"]
        rejected = state["rejected"]
        failed_api = state["failed_api"]
        print(f"\n[Resume] Continuing from index {start_index} "
              f"(accepted: {accepted}, rejected: {rejected}, api_fails: {failed_api})")
    else:
        start_index = 0
        accepted = 0
        rejected = 0
        failed_api = 0
        print(f"\n[Start] Beginning fresh fetch...")

    print()

    for i in range(start_index, total_candidates):
        if _stop_requested:
            _save_paused_state(i, accepted, rejected, failed_api, total_candidates)
            return

        if accepted >= target_count:
            print(f"\n[Done] Reached target of {target_count} accepted sites!")
            _save_completed_state(i, accepted, rejected, failed_api, total_candidates)
            return

        cand = candidates[i]
        progress = f"[{i + 1}/{total_candidates}]"
        label = f"{cand['city']}/{cand['zone']}"

        # Rate limiting — random delay between requests
        if i > start_index:
            delay = random.uniform(MIN_DELAY, MAX_DELAY)
            time.sleep(delay)

        # Fetch from Overpass
        print(f"{progress} Fetching {label} ({cand['lat']:.4f}, {cand['lon']:.4f})...", end=" ", flush=True)

        result = fetch_overpass(cand["lat"], cand["lon"], radius, cand["default_height"])

        if result is None:
            failed_api += 1
            print(f"✗ API failed")
            # On API failure, extra backoff
            time.sleep(BACKOFF_DELAY)
            continue

        buildings = result["buildings"]
        roads = result["roads"]

        # Separate site building (closest to center) from context
        buildings.sort(key=lambda b: b["dist_to_center"])

        if len(buildings) < 2:
            rejected += 1
            print(f"✗ rejected (only {len(buildings)} building(s))")
            continue

        site_building = buildings[0]
        context_buildings = buildings[1:]

        # Check site parcel area
        try:
            from shapely.geometry import Polygon
            sp = Polygon(site_building["vertices_2d"])
            if not sp.is_valid:
                sp = sp.buffer(0)
            site_area_m2 = round(float(sp.area), 1)
        except Exception:
            site_area_m2 = 0.0

        if site_area_m2 < MIN_SITE_AREA:
            rejected += 1
            print(f"✗ rejected (site area too small: {site_area_m2:.1f} m² < {MIN_SITE_AREA} m²)")
            continue

        area_tier = compute_area_tier(site_area_m2)

        # Quality check on context buildings
        ok, reason, metrics = evaluate_site(context_buildings, radius)

        if not ok:
            rejected += 1
            print(f"✗ rejected ({reason})")
            continue

        metrics["site_area_m2"] = site_area_m2
        metrics["area_tier"] = area_tier

        # Accepted! Store in database
        site_data = {
            "buildings": [
                {
                    "id": b["id"],
                    "name": b["name"],
                    "vertices_2d": b["vertices_2d"],
                    "centroid": b["centroid"],
                    "height": b["height"],
                    "height_source": b["height_source"],
                }
                for b in context_buildings
            ],
            "roads": roads,
            "site_boundary": {
                "name": site_building["name"],
                "vertices_2d": site_building["vertices_2d"],
                "centroid": site_building["centroid"],
                "original_height": site_building["height"],
            },
        }

        cand_info = {
            **cand,
            "radius_m": radius,
        }

        site_id = add_site(site_data, metrics, cand_info)
        accepted += 1
        print(f"✓ {site_id} — FAR={metrics['far']}, bldgs={metrics['building_count']}, "
              f"maxH={metrics['max_height']}m  [{accepted}/{target_count}]")

        # Save state periodically (every 10 candidates)
        if i % 10 == 0:
            save_fetch_state({
                "status": "running",
                "total_candidates": total_candidates,
                "current_index": i + 1,
                "accepted": accepted,
                "rejected": rejected,
                "failed_api": failed_api,
                "target_count": target_count,
            })

    # All candidates exhausted
    print(f"\n[Done] Exhausted all {total_candidates} candidates.")
    _save_completed_state(total_candidates, accepted, rejected, failed_api, total_candidates)


def _save_paused_state(index, accepted, rejected, failed_api, total):
    save_fetch_state({
        "status": "paused",
        "total_candidates": total,
        "current_index": index,
        "accepted": accepted,
        "rejected": rejected,
        "failed_api": failed_api,
    })
    print(f"\n[Saved] State saved — {accepted} accepted, {rejected} rejected, {failed_api} API failures.")
    print(f"        Resume with: python batch_fetcher.py")


def _save_completed_state(index, accepted, rejected, failed_api, total):
    save_fetch_state({
        "status": "completed",
        "total_candidates": total,
        "current_index": index,
        "accepted": accepted,
        "rejected": rejected,
        "failed_api": failed_api,
    })
    print(f"\n{'=' * 70}")
    print(f"  FETCH COMPLETE")
    print(f"  Accepted : {accepted}")
    print(f"  Rejected : {rejected}")
    print(f"  API Fail : {failed_api}")
    print(f"{'=' * 70}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Batch-fetch urban context sites from OpenStreetMap"
    )
    parser.add_argument(
        "--target", type=int, default=500,
        help="Stop after accepting this many sites (default: 500)"
    )
    parser.add_argument(
        "--radius", type=float, default=100.0,
        help="Context radius in meters (default: 100)"
    )
    parser.add_argument(
        "--spacing", type=float, default=250.0,
        help="Grid spacing between sample points in meters (default: 250)"
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Clear previous state and start fresh"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview candidate points without actually fetching"
    )

    args = parser.parse_args()

    if args.dry_run:
        candidates = get_all_candidate_points(spacing_m=args.spacing)
        print(f"Total candidate points: {len(candidates)}")
        from collections import Counter
        city_counts = Counter(c["city"] for c in candidates)
        print("\nBy city:")
        for city, count in sorted(city_counts.items(), key=lambda x: -x[1]):
            print(f"  {city:20s} : {count}")
        tier_counts = Counter(c["density_tier"] for c in candidates)
        print("\nBy density tier:")
        for tier, count in sorted(tier_counts.items()):
            print(f"  {tier:20s} : {count}")
        return

    run_batch_fetch(
        target_count=args.target,
        radius=args.radius,
        spacing=args.spacing,
        reset=args.reset,
    )


if __name__ == "__main__":
    main()
