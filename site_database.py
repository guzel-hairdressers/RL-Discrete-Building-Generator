"""
Site Database — File & SQLite database manager for Context Generator dataset.
Stores site geometry (JSON), site metadata/metrics (SQLite), and fetch state (JSON).
"""

import os
import json
import sqlite3
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, "database")
SITES_DIR = os.path.join(DB_DIR, "sites")
INDEX_DB_PATH = os.path.join(DB_DIR, "context_dataset.db")
STATE_FILE_PATH = os.path.join(DB_DIR, "fetch_state.json")


def ensure_dirs():
    """Ensure database directories exist and SQLite database schema is initialized."""
    os.makedirs(SITES_DIR, exist_ok=True)
    _init_sqlite_db()


def _init_sqlite_db():
    conn = sqlite3.connect(INDEX_DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sites (
        site_id TEXT PRIMARY KEY,
        city TEXT NOT NULL,
        zone TEXT NOT NULL,
        lat REAL NOT NULL,
        lon REAL NOT NULL,
        site_area_m2 REAL NOT NULL,
        area_tier TEXT NOT NULL,
        far REAL NOT NULL,
        gcr REAL NOT NULL,
        building_count INTEGER NOT NULL,
        max_height_m REAL NOT NULL,
        avg_height_m REAL NOT NULL,
        density_tier TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """)

    conn.commit()
    conn.close()


def add_site(site_data, metrics, cand_info):
    """
    Save a new site to database.
    Returns generated site_id (e.g. site_0001).
    """
    ensure_dirs()
    conn = sqlite3.connect(INDEX_DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM sites")
    count = cursor.fetchone()[0]
    site_id = f"site_{count + 1:04d}"

    now_str = datetime.now(timezone.utc).isoformat()
    site_file = os.path.join(SITES_DIR, f"{site_id}.json")

    full_record = {
        "site_id": site_id,
        "created_at": now_str,
        "city": cand_info["city"],
        "zone": cand_info["zone"],
        "density_tier": cand_info.get("density_tier", "high"),
        "coordinates": {
            "lat": cand_info["lat"],
            "lon": cand_info["lon"],
        },
        "radius_m": cand_info.get("radius_m", 100.0),
        "metrics": metrics,
        "site_boundary": site_data["site_boundary"],
        "context_buildings": site_data["buildings"],
        "roads": site_data.get("roads", []),
    }

    with open(site_file, "w") as f:
        json.dump(full_record, f, indent=2)

    cursor.execute("""
    INSERT INTO sites (
        site_id, city, zone, lat, lon, site_area_m2, area_tier,
        far, gcr, building_count, max_height_m, avg_height_m, density_tier, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        site_id,
        cand_info["city"],
        cand_info["zone"],
        cand_info["lat"],
        cand_info["lon"],
        metrics.get("site_area_m2", 0.0),
        metrics.get("area_tier", "M"),
        metrics.get("far", 0.0),
        metrics.get("gcr", 0.0),
        metrics.get("building_count", len(site_data["buildings"])),
        metrics.get("max_height", 0.0),
        metrics.get("avg_height", 0.0),
        cand_info.get("density_tier", "high"),
        now_str,
    ))

    conn.commit()
    conn.close()
    return site_id


def load_site(site_id):
    """Load complete JSON record for site_id."""
    path = os.path.join(SITES_DIR, f"{site_id}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return json.load(f)


def list_sites(limit=50, city=None):
    """List site records from SQLite index."""
    ensure_dirs()
    conn = sqlite3.connect(INDEX_DB_PATH)
    cursor = conn.cursor()

    if city:
        cursor.execute("SELECT * FROM sites WHERE city=? ORDER BY site_id LIMIT ?", (city, limit))
    else:
        cursor.execute("SELECT * FROM sites ORDER BY site_id LIMIT ?", (limit,))

    rows = cursor.fetchall()
    conn.close()
    return rows


def load_fetch_state():
    """Load fetcher state from JSON file."""
    if not os.path.exists(STATE_FILE_PATH):
        return None
    try:
        with open(STATE_FILE_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return None


def save_fetch_state(state):
    """Save fetcher state to JSON file."""
    ensure_dirs()
    with open(STATE_FILE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def clear_fetch_state():
    """Remove fetch state file."""
    if os.path.exists(STATE_FILE_PATH):
        os.remove(STATE_FILE_PATH)
