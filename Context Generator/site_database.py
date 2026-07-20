"""
Site Database — Simple file-based database for storing extracted urban context sites.

Structure:
    database/
    ├── index.json              # Master index with summary metrics for all sites
    ├── fetch_state.json        # Pause/resume state for batch fetcher
    └── sites/
        ├── site_0001.json      # Full site data
        ├── site_0002.json
        └── ...
"""

import json
import os
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_DIR = os.path.join(BASE_DIR, "database")
SITES_DIR = os.path.join(DATABASE_DIR, "sites")
INDEX_FILE = os.path.join(DATABASE_DIR, "index.json")
FETCH_STATE_FILE = os.path.join(DATABASE_DIR, "fetch_state.json")


def ensure_dirs():
    """Create database directories if they don't exist."""
    os.makedirs(SITES_DIR, exist_ok=True)


def _load_index():
    """Load the master index file."""
    if os.path.exists(INDEX_FILE):
        with open(INDEX_FILE, "r") as f:
            return json.load(f)
    return {"total_sites": 0, "sites": []}


def _save_index(index_data):
    """Save the master index file."""
    ensure_dirs()
    with open(INDEX_FILE, "w") as f:
        json.dump(index_data, f, indent=2)


def get_next_site_id():
    """Return the next available site ID (e.g., 'site_0001')."""
    index = _load_index()
    num = index["total_sites"] + 1
    return f"site_{num:04d}"


def add_site(site_data, metrics, candidate_info):
    """
    Store an accepted site in the database.

    Args:
        site_data: dict with keys: buildings, roads, site_boundary, coordinates, etc.
        metrics: dict from compute_quick_metrics or compute_urban_metrics
        candidate_info: dict with: city, zone, lat, lon, density_tier, typology
    """
    ensure_dirs()
    index = _load_index()

    site_id = f"site_{index['total_sites'] + 1:04d}"

    site_area_m2 = metrics.get("site_area_m2", site_data.get("site_area_m2", 0.0))
    area_tier = metrics.get("area_tier", site_data.get("area_tier", "M"))

    # Build the full site record
    site_record = {
        "id": site_id,
        "city": candidate_info["city"],
        "zone": candidate_info["zone"],
        "coordinates": {"lat": candidate_info["lat"], "lon": candidate_info["lon"]},
        "density_tier": candidate_info["density_tier"],
        "typology": candidate_info["typology"],
        "area_tier": area_tier,
        "site_area_m2": site_area_m2,
        "default_height": candidate_info.get("default_height", 30.0),
        "radius_m": candidate_info.get("radius_m", 100.0),
        "verification_links": {
            "google_maps": f"https://www.google.com/maps?q={candidate_info['lat']},{candidate_info['lon']}",
            "openstreetmap": f"https://www.openstreetmap.org/#map=18/{candidate_info['lat']}/{candidate_info['lon']}",
        },
        "site_boundary": site_data.get("site_boundary", {}),
        "context_buildings": site_data.get("buildings", []),
        "roads": site_data.get("roads", []),
        "metrics": metrics,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

    # Save full site file
    site_file = os.path.join(SITES_DIR, f"{site_id}.json")
    with open(site_file, "w") as f:
        json.dump(site_record, f, indent=2)

    # Add summary to index
    index_entry = {
        "id": site_id,
        "city": candidate_info["city"],
        "zone": candidate_info["zone"],
        "lat": candidate_info["lat"],
        "lon": candidate_info["lon"],
        "typology": candidate_info["typology"],
        "density_tier": candidate_info["density_tier"],
        "area_tier": area_tier,
        "site_area_m2": site_area_m2,
        "far": metrics.get("far", 0.0),
        "gcr": metrics.get("gcr", 0.0),
        "building_count": metrics.get("building_count", 0),
        "max_height": metrics.get("max_height", 0.0),
        "avg_height": metrics.get("avg_height", 0.0),
    }
    index["sites"].append(index_entry)
    index["total_sites"] = len(index["sites"])
    _save_index(index)

    return site_id


def load_site(site_id):
    """Load full site data by ID."""
    site_file = os.path.join(SITES_DIR, f"{site_id}.json")
    if not os.path.exists(site_file):
        raise FileNotFoundError(f"Site '{site_id}' not found at {site_file}")
    with open(site_file, "r") as f:
        return json.load(f)


def list_sites(sort_by="far", descending=True, density_tier=None, city=None, typology=None):
    """
    List all sites in the index, optionally filtered and sorted.

    Args:
        sort_by: field name to sort by (e.g., 'far', 'building_count', 'max_height')
        descending: sort order
        density_tier: filter to specific tier ('mid', 'high', 'very_high')
        city: filter to specific city
        typology: filter to specific typology ('strict_grid', 'organic')

    Returns:
        list of site summary dicts
    """
    index = _load_index()
    sites = index["sites"]

    if density_tier:
        sites = [s for s in sites if s.get("density_tier") == density_tier]
    if city:
        sites = [s for s in sites if s.get("city") == city]
    if typology:
        sites = [s for s in sites if s.get("typology") == typology]

    sites.sort(key=lambda s: s.get(sort_by, 0), reverse=descending)
    return sites


def get_stats():
    """Return aggregate statistics about the database."""
    index = _load_index()
    sites = index["sites"]

    if not sites:
        return {"total": 0}

    from collections import Counter

    city_counts = Counter(s["city"] for s in sites)
    tier_counts = Counter(s["density_tier"] for s in sites)
    typology_counts = Counter(s["typology"] for s in sites)

    fars = [s["far"] for s in sites]
    heights = [s["max_height"] for s in sites]
    bldg_counts = [s["building_count"] for s in sites]

    return {
        "total": len(sites),
        "by_city": dict(city_counts.most_common()),
        "by_density_tier": dict(tier_counts.most_common()),
        "by_typology": dict(typology_counts.most_common()),
        "far_range": (min(fars), max(fars)),
        "far_mean": round(sum(fars) / len(fars), 2),
        "max_height_range": (min(heights), max(heights)),
        "avg_building_count": round(sum(bldg_counts) / len(bldg_counts), 1),
    }


# --- Fetch State Management (Pause/Resume) ---

def load_fetch_state():
    """Load the fetch state file for pause/resume."""
    if os.path.exists(FETCH_STATE_FILE):
        with open(FETCH_STATE_FILE, "r") as f:
            return json.load(f)
    return None


def save_fetch_state(state):
    """Save the fetch state file."""
    ensure_dirs()
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(FETCH_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def clear_fetch_state():
    """Remove the fetch state file (for --reset)."""
    if os.path.exists(FETCH_STATE_FILE):
        os.remove(FETCH_STATE_FILE)
