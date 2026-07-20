"""
City Targets — Master list of known high-density urban zones worldwide.

Each zone defines a bounding box (lat/lon) within which sample points are
generated on a regular grid (~250m spacing). The fetcher queries OSM for
building context at each sample point and applies quality filters.

Zones are categorised by:
  - density_tier: "mid" | "high" | "very_high"  (expected, verified post-fetch)
  - typology:     "strict_grid" | "organic"
"""

URBAN_ZONES = [
    # =========================================================================
    #  STRICT GRID CITIES
    # =========================================================================

    # --- New York City ---
    {
        "city": "nyc",
        "zone": "midtown_east",
        "density_tier": "very_high",
        "typology": "strict_grid",
        "bbox": (40.7490, -73.9800, 40.7600, -73.9680),
        "default_height": 80.0,
    },
    {
        "city": "nyc",
        "zone": "midtown_west",
        "density_tier": "very_high",
        "typology": "strict_grid",
        "bbox": (40.7540, -73.9950, 40.7640, -73.9830),
        "default_height": 90.0,
    },
    {
        "city": "nyc",
        "zone": "financial_district",
        "density_tier": "very_high",
        "typology": "strict_grid",
        "bbox": (40.7030, -74.0150, 40.7120, -74.0040),
        "default_height": 100.0,
    },
    {
        "city": "nyc",
        "zone": "upper_east_side",
        "density_tier": "high",
        "typology": "strict_grid",
        "bbox": (40.7630, -73.9700, 40.7740, -73.9560),
        "default_height": 40.0,
    },

    # --- Chicago ---
    {
        "city": "chicago",
        "zone": "loop",
        "density_tier": "very_high",
        "typology": "strict_grid",
        "bbox": (41.8740, -87.6380, 41.8860, -87.6230),
        "default_height": 70.0,
    },
    {
        "city": "chicago",
        "zone": "river_north",
        "density_tier": "high",
        "typology": "strict_grid",
        "bbox": (41.8870, -87.6380, 41.8970, -87.6260),
        "default_height": 50.0,
    },

    # --- Barcelona ---
    {
        "city": "barcelona",
        "zone": "eixample_central",
        "density_tier": "mid",
        "typology": "strict_grid",
        "bbox": (41.3850, 2.1550, 41.3970, 2.1720),
        "default_height": 22.0,
    },
    {
        "city": "barcelona",
        "zone": "eixample_north",
        "density_tier": "mid",
        "typology": "strict_grid",
        "bbox": (41.3970, 2.1580, 41.4060, 2.1730),
        "default_height": 22.0,
    },

    # --- Buenos Aires ---
    {
        "city": "buenos_aires",
        "zone": "microcentro",
        "density_tier": "high",
        "typology": "strict_grid",
        "bbox": (-34.6080, -58.3800, -34.5980, -58.3680),
        "default_height": 35.0,
    },
    {
        "city": "buenos_aires",
        "zone": "retiro",
        "density_tier": "high",
        "typology": "strict_grid",
        "bbox": (-34.5980, -58.3800, -34.5880, -58.3680),
        "default_height": 40.0,
    },

    # --- Melbourne ---
    {
        "city": "melbourne",
        "zone": "cbd",
        "density_tier": "high",
        "typology": "strict_grid",
        "bbox": (-37.8180, 144.9550, -37.8080, 144.9720),
        "default_height": 45.0,
    },

    # =========================================================================
    #  ORGANIC / IRREGULAR CITIES
    # =========================================================================

    # --- Tokyo ---
    {
        "city": "tokyo",
        "zone": "shinjuku",
        "density_tier": "very_high",
        "typology": "organic",
        "bbox": (35.6880, 139.6930, 35.6990, 139.7080),
        "default_height": 60.0,
    },
    {
        "city": "tokyo",
        "zone": "shibuya",
        "density_tier": "high",
        "typology": "organic",
        "bbox": (35.6560, 139.6960, 35.6650, 139.7070),
        "default_height": 45.0,
    },
    {
        "city": "tokyo",
        "zone": "minato_roppongi",
        "density_tier": "high",
        "typology": "organic",
        "bbox": (35.6570, 139.7260, 35.6670, 139.7400),
        "default_height": 50.0,
    },

    # --- Hong Kong ---
    {
        "city": "hongkong",
        "zone": "central",
        "density_tier": "very_high",
        "typology": "organic",
        "bbox": (22.2770, 114.1500, 22.2860, 114.1650),
        "default_height": 120.0,
    },
    {
        "city": "hongkong",
        "zone": "kowloon_tsimshatsui",
        "density_tier": "very_high",
        "typology": "organic",
        "bbox": (22.2920, 114.1650, 22.3030, 114.1800),
        "default_height": 80.0,
    },
    {
        "city": "hongkong",
        "zone": "mongkok",
        "density_tier": "high",
        "typology": "organic",
        "bbox": (22.3150, 114.1650, 22.3260, 114.1770),
        "default_height": 50.0,
    },

    # --- London ---
    {
        "city": "london",
        "zone": "city_of_london",
        "density_tier": "high",
        "typology": "organic",
        "bbox": (51.5090, -0.0990, 51.5180, -0.0780),
        "default_height": 45.0,
    },
    {
        "city": "london",
        "zone": "canary_wharf",
        "density_tier": "very_high",
        "typology": "organic",
        "bbox": (51.5010, -0.0250, 51.5080, -0.0130),
        "default_height": 100.0,
    },

    # --- Singapore ---
    {
        "city": "singapore",
        "zone": "cbd_raffles",
        "density_tier": "very_high",
        "typology": "organic",
        "bbox": (1.2770, 103.8460, 1.2870, 103.8580),
        "default_height": 90.0,
    },
    {
        "city": "singapore",
        "zone": "tanjong_pagar",
        "density_tier": "high",
        "typology": "organic",
        "bbox": (1.2700, 103.8380, 1.2790, 103.8500),
        "default_height": 60.0,
    },

    # --- Seoul ---
    {
        "city": "seoul",
        "zone": "gangnam",
        "density_tier": "high",
        "typology": "organic",
        "bbox": (37.4950, 127.0250, 37.5060, 127.0420),
        "default_height": 40.0,
    },
    {
        "city": "seoul",
        "zone": "jongno_cbd",
        "density_tier": "high",
        "typology": "organic",
        "bbox": (37.5650, 126.9750, 37.5750, 126.9900),
        "default_height": 45.0,
    },

    # --- São Paulo ---
    {
        "city": "sao_paulo",
        "zone": "paulista",
        "density_tier": "high",
        "typology": "organic",
        "bbox": (-23.5650, -46.6620, -23.5530, -46.6460),
        "default_height": 50.0,
    },
    {
        "city": "sao_paulo",
        "zone": "faria_lima",
        "density_tier": "high",
        "typology": "organic",
        "bbox": (-23.5780, -46.6920, -23.5680, -46.6780),
        "default_height": 55.0,
    },
]


def generate_sample_points(zone, spacing_m=250.0):
    """
    Generate a regular grid of (lat, lon) sample points within a zone's bounding box.

    Args:
        zone: dict with 'bbox' key as (min_lat, min_lon, max_lat, max_lon)
        spacing_m: approximate spacing between sample points in meters

    Returns:
        list of (lat, lon) tuples
    """
    import math

    min_lat, min_lon, max_lat, max_lon = zone["bbox"]

    # Convert spacing from meters to approximate degrees
    # 1 degree latitude ≈ 111,320 m
    lat_step = spacing_m / 111320.0
    # 1 degree longitude ≈ 111,320 * cos(lat) m
    mid_lat = (min_lat + max_lat) / 2.0
    lon_step = spacing_m / (111320.0 * math.cos(math.radians(mid_lat)))

    points = []
    lat = min_lat
    while lat <= max_lat:
        lon = min_lon
        while lon <= max_lon:
            points.append((round(lat, 6), round(lon, 6)))
            lon += lon_step
        lat += lat_step

    return points


def get_all_candidate_points(spacing_m=250.0):
    """
    Generate all candidate sample points across all urban zones.

    Returns:
        list of dicts:
        [
            {
                "lat": 40.7580,
                "lon": -73.9855,
                "city": "nyc",
                "zone": "midtown_east",
                "density_tier": "very_high",
                "typology": "strict_grid",
                "default_height": 80.0,
            },
            ...
        ]
    """
    candidates = []
    for zone in URBAN_ZONES:
        points = generate_sample_points(zone, spacing_m=spacing_m)
        for lat, lon in points:
            candidates.append({
                "lat": lat,
                "lon": lon,
                "city": zone["city"],
                "zone": zone["zone"],
                "density_tier": zone["density_tier"],
                "typology": zone["typology"],
                "default_height": zone["default_height"],
            })
    return candidates


if __name__ == "__main__":
    candidates = get_all_candidate_points()
    print(f"Total candidate sample points: {len(candidates)}")
    print()

    # Breakdown by city
    from collections import Counter
    city_counts = Counter(c["city"] for c in candidates)
    for city, count in sorted(city_counts.items(), key=lambda x: -x[1]):
        print(f"  {city:20s} : {count} points")

    print()
    tier_counts = Counter(c["density_tier"] for c in candidates)
    for tier, count in sorted(tier_counts.items()):
        print(f"  {tier:20s} : {count} points")
