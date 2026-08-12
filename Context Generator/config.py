"""
Configuration settings and target city presets for Context Generator.
"""

import os

# Default directory for outputs
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "app", "public", "sites")
DATASET_DIR = os.path.join(BASE_DIR, "app", "public", "data")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(DATASET_DIR, exist_ok=True)

# Default context extraction radius in meters
DEFAULT_RADIUS = 100.0  # 100m radius context = 200m x 200m area around central site

# Target City Presets for OSM Extraction
TARGET_CITIES = {
    # --- Strict Grid / Orthogonal Cities ---
    "nyc_midtown": {
        "name": "New York City (Midtown Manhattan)",
        "city_code": "nyc",
        "typology": "strict_grid",
        "density_class": "superhigh_density",
        "lat": 40.7580,
        "lon": -73.9855,
        "default_height": 120.0,
    },
    "barcelona_eixample": {
        "name": "Barcelona (Eixample)",
        "city_code": "bcn",
        "typology": "strict_grid",
        "density_class": "mid_density",
        "lat": 41.3917,
        "lon": 2.1649,
        "default_height": 22.0,
    },
    "chicago_loop": {
        "name": "Chicago (The Loop)",
        "city_code": "chi",
        "typology": "strict_grid",
        "density_class": "high_density",
        "lat": 41.8781,
        "lon": -87.6298,
        "default_height": 85.0,
    },
    
    # --- Organic / Relaxed / Natural Layout Cities ---
    "tokyo_shinjuku": {
        "name": "Tokyo (Shinjuku)",
        "city_code": "tokyo",
        "typology": "organic",
        "density_class": "high_density",
        "lat": 35.6938,
        "lon": 139.7034,
        "default_height": 65.0,
    },
    "london_city": {
        "name": "London (City of London)",
        "city_code": "ldn",
        "typology": "organic",
        "density_class": "high_density",
        "lat": 51.5128,
        "lon": -0.0918,
        "default_height": 45.0,
    },
    "hongkong_central": {
        "name": "Hong Kong (Central)",
        "city_code": "hk",
        "typology": "organic_constrained",
        "density_class": "superhigh_density",
        "lat": 22.2819,
        "lon": 114.1581,
        "default_height": 140.0,
    },
    "paris_center": {
        "name": "Paris (Palais-Royal / Opéra)",
        "city_code": "prs",
        "typology": "perimeter_block",
        "density_class": "mid_density",
        "lat": 48.8656,
        "lon": 2.3364,
        "default_height": 24.0,
    },
    "singapore_cbd": {
        "name": "Singapore (Raffles Place)",
        "city_code": "sgp",
        "typology": "highrise_garden",
        "density_class": "superhigh_density",
        "lat": 1.2839,
        "lon": 103.8515,
        "default_height": 160.0,
    },
}

# Density Class Profiles for Procedural Generation
DENSITY_PROFILES = {
    "mid_density": {
        "building_height_range": (12.0, 35.0),    # meters
        "building_coverage": 0.45,                 # ~45% ground coverage
        "far_target": (2.0, 4.0),                  # Floor Area Ratio
        "min_building_gap": 6.0,                   # meters gap
        "street_width": 12.0,                      # meters
        "site_area_range": (800.0, 2500.0),        # m² for site boundary
    },
    "high_density": {
        "building_height_range": (35.0, 90.0),
        "building_coverage": 0.60,
        "far_target": (4.5, 8.5),
        "min_building_gap": 5.0,
        "street_width": 14.0,
        "site_area_range": (1200.0, 4000.0),
    },
    "superhigh_density": {
        "building_height_range": (80.0, 280.0),
        "building_coverage": 0.70,
        "far_target": (9.0, 22.0),
        "min_building_gap": 4.0,
        "street_width": 16.0,
        "site_area_range": (1500.0, 6000.0),
    },
}
