"""
City Targets — High-density urban sampling target coordinates across major global cities.
"""

import math

CITY_TARGETS = {
    "tokyo": [
        {"zone": "shibuya", "lat": 35.6580, "lon": 139.7016, "radius": 400, "density_tier": "very_high", "default_height": 30.0},
        {"zone": "shinjuku", "lat": 35.6909, "lon": 139.7003, "radius": 400, "density_tier": "very_high", "default_height": 35.0},
        {"zone": "ginza", "lat": 35.6719, "lon": 139.7648, "radius": 350, "density_tier": "very_high", "default_height": 28.0},
        {"zone": "roppongi", "lat": 35.6628, "lon": 139.7314, "radius": 350, "density_tier": "high", "default_height": 25.0},
        {"zone": "akihabara", "lat": 35.6983, "lon": 139.7731, "radius": 350, "density_tier": "high", "default_height": 22.0},
    ],
    "nyc": [
        {"zone": "midtown_east", "lat": 40.7549, "lon": -73.9740, "radius": 450, "density_tier": "very_high", "default_height": 45.0},
        {"zone": "financial_district", "lat": 40.7075, "lon": -74.0089, "radius": 400, "density_tier": "very_high", "default_height": 50.0},
        {"zone": "chelsea", "lat": 40.7465, "lon": -74.0014, "radius": 400, "density_tier": "high", "default_height": 28.0},
        {"zone": "soho", "lat": 40.7233, "lon": -74.0030, "radius": 350, "density_tier": "high", "default_height": 22.0},
        {"zone": "upper_east_side", "lat": 40.7736, "lon": -73.9566, "radius": 400, "density_tier": "very_high", "default_height": 35.0},
    ],
    "hongkong": [
        {"zone": "central", "lat": 22.2819, "lon": 114.1581, "radius": 400, "density_tier": "very_high", "default_height": 55.0},
        {"zone": "causeway_bay", "lat": 22.2800, "lon": 114.1850, "radius": 400, "density_tier": "very_high", "default_height": 45.0},
        {"zone": "mong_kok", "lat": 22.3193, "lon": 114.1694, "radius": 400, "density_tier": "very_high", "default_height": 40.0},
        {"zone": "tsim_sha_tsui", "lat": 22.2988, "lon": 114.1722, "radius": 350, "density_tier": "very_high", "default_height": 35.0},
    ],
    "london": [
        {"zone": "city_of_london", "lat": 51.5128, "lon": -0.0918, "radius": 400, "density_tier": "high", "default_height": 28.0},
        {"zone": "canary_wharf", "lat": 51.5050, "lon": -0.0200, "radius": 350, "density_tier": "very_high", "default_height": 45.0},
        {"zone": "soho_west_end", "lat": 51.5137, "lon": -0.1337, "radius": 350, "density_tier": "high", "default_height": 22.0},
    ],
    "barcelona": [
        {"zone": "eixample_right", "lat": 41.3925, "lon": 2.1648, "radius": 450, "density_tier": "high", "default_height": 22.0},
        {"zone": "eixample_left", "lat": 41.3875, "lon": 2.1550, "radius": 450, "density_tier": "high", "default_height": 22.0},
        {"zone": "poblenou", "lat": 41.4000, "lon": 2.2000, "radius": 400, "density_tier": "mid", "default_height": 18.0},
    ],
    "singapore": [
        {"zone": "marina_bay", "lat": 1.2800, "lon": 103.8500, "radius": 400, "density_tier": "very_high", "default_height": 45.0},
        {"zone": "orchard", "lat": 1.3038, "lon": 103.8358, "radius": 350, "density_tier": "high", "default_height": 30.0},
    ],
    "seoul": [
        {"zone": "gangnam", "lat": 37.4979, "lon": 127.0276, "radius": 400, "density_tier": "very_high", "default_height": 40.0},
        {"zone": "myeongdong", "lat": 37.5636, "lon": 126.9827, "radius": 350, "density_tier": "very_high", "default_height": 30.0},
        {"zone": "yeouido", "lat": 37.5219, "lon": 126.9242, "radius": 400, "density_tier": "very_high", "default_height": 45.0},
    ],
}


def get_all_candidate_points(spacing_m=250.0):
    """
    Generate sampling grid candidate points around all city target centers.
    """
    candidates = []
    # Approx meters per degree
    M_PER_DEG_LAT = 111000.0

    for city, zones in CITY_TARGETS.items():
        for z in zones:
            lat0 = z["lat"]
            lon0 = z["lon"]
            r_m = z["radius"]
            m_per_deg_lon = M_PER_DEG_LAT * math.cos(math.radians(lat0))

            steps = int(r_m / spacing_m)
            for dx in range(-steps, steps + 1):
                for dy in range(-steps, steps + 1):
                    x_m = dx * spacing_m
                    y_m = dy * spacing_m
                    if math.hypot(x_m, y_m) <= r_m:
                        c_lat = lat0 + (y_m / M_PER_DEG_LAT)
                        c_lon = lon0 + (x_m / m_per_deg_lon)
                        candidates.append({
                            "city": city,
                            "zone": z["zone"],
                            "lat": c_lat,
                            "lon": c_lon,
                            "density_tier": z["density_tier"],
                            "default_height": z["default_height"],
                        })

    return candidates
