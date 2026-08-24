"""
Procedural Urban Context Generator module.
Synthesizes 3D building sites and surrounding context blocks (160m radius)
for solar and building performance simulations based on density profiles and urban typologies.
"""

import math
import random
import numpy as np

from config import DENSITY_PROFILES, DEFAULT_RADIUS
from geometry_3d import extrude_polygon_to_3d_mesh, compute_urban_metrics

try:
    from shapely.geometry import Polygon, MultiPolygon, Point, box
    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False


class ProceduralContextGenerator:
    def __init__(self, seed=None):
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)

    def generate_site_boundary(self, target_area=2000.0, aspect_ratio=1.2, rotation_deg=0.0):
        width = math.sqrt(target_area / aspect_ratio)
        height = target_area / width
        hw, hh = width / 2.0, height / 2.0

        base_verts = [
            [-hw, -hh],
            [hw, -hh],
            [hw, hh],
            [-hw, hh]
        ]

        if rotation_deg != 0.0:
            rad = math.radians(rotation_deg)
            cos_a, sin_a = math.cos(rad), math.sin(rad)
            rotated_verts = []
            for x, y in base_verts:
                rx = x * cos_a - y * sin_a
                ry = x * sin_a + y * cos_a
                rotated_verts.append([round(rx, 2), round(ry, 2)])
            base_verts = rotated_verts

        return base_verts

    def generate_context_scene(self, density_class="high_density", typology="strict_grid", radius=DEFAULT_RADIUS, seed=None):
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)

        profile = DENSITY_PROFILES.get(density_class, DENSITY_PROFILES["high_density"])
        min_h, max_h = profile["building_height_range"]
        street_w = profile["street_width"]
        min_gap = profile["min_building_gap"]

        site_area = random.uniform(*profile["site_area_range"])
        aspect = random.uniform(0.8, 1.6)
        rot = random.choice([0.0, 15.0, 30.0, 45.0, 90.0]) if typology == "organic" else 0.0
        site_verts = self.generate_site_boundary(target_area=site_area, aspect_ratio=aspect, rotation_deg=rot)

        if typology == "strict_grid":
            context_buildings = self._generate_grid_buildings(site_verts, profile, radius, min_h, max_h, street_w, min_gap)
        elif typology == "organic":
            context_buildings = self._generate_organic_buildings(site_verts, profile, radius, min_h, max_h, street_w, min_gap)
        elif typology == "superhigh_tower":
            context_buildings = self._generate_tower_cluster_buildings(site_verts, profile, radius, min_h, max_h, street_w, min_gap)
        else:
            context_buildings = self._generate_grid_buildings(site_verts, profile, radius, min_h, max_h, street_w, min_gap)

        metrics = compute_urban_metrics(site_verts, context_buildings, radius_m=radius)

        scene = {
            "density_class": density_class,
            "typology": typology,
            "radius_m": radius,
            "site_boundary": {
                "vertices_2d": site_verts,
                "centroid": [0.0, 0.0],
                "area_m2": metrics["site_area_m2"]
            },
            "context_buildings": context_buildings,
            "metrics": metrics
        }

        return scene

    def _generate_grid_buildings(self, site_verts, profile, radius, min_h, max_h, street_w, min_gap):
        buildings = []
        block_step = 42.0

        for ix in range(-3, 4):
            for iy in range(-3, 4):
                cx = ix * block_step
                cy = iy * block_step
                dist = math.hypot(cx, cy)

                if (abs(ix) <= 0 and abs(iy) <= 0) or dist > radius:
                    continue

                bw = random.uniform(22.0, 32.0)
                bh = random.uniform(22.0, 32.0)

                b_verts = [
                    [round(cx - bw/2, 2), round(cy - bh/2, 2)],
                    [round(cx + bw/2, 2), round(cy - bh/2, 2)],
                    [round(cx + bw/2, 2), round(cy + bh/2, 2)],
                    [round(cx - bw/2, 2), round(cy + bh/2, 2)],
                ]

                if math.hypot(cx, cy) < street_w + 10.0:
                    continue

                height = round(random.uniform(min_h, max_h), 1)
                mesh_3d = extrude_polygon_to_3d_mesh(b_verts, height)

                buildings.append({
                    "id": f"grid_b_{len(buildings)}",
                    "vertices_2d": b_verts,
                    "height": height,
                    "mesh_3d": mesh_3d,
                    "centroid": [cx, cy, 0.0]
                })

        return buildings

    def _generate_organic_buildings(self, site_verts, profile, radius, min_h, max_h, street_w, min_gap):
        buildings = []
        rings = [30.0, 60.0, 90.0, 130.0]

        for r_idx, r_dist in enumerate(rings):
            if r_dist > radius:
                continue
            count = int(r_dist / 6.0)
            angle_step = (2 * math.pi) / count
            rot_offset = random.uniform(0, math.pi)

            for i in range(count):
                angle = i * angle_step + rot_offset
                r_actual = r_dist + random.uniform(-4.0, 4.0)
                cx = r_actual * math.cos(angle)
                cy = r_actual * math.sin(angle)

                if math.hypot(cx, cy) > radius or math.hypot(cx, cy) < street_w + 8.0:
                    continue

                bw = random.uniform(14.0, 26.0)
                bh = random.uniform(14.0, 26.0)

                tangent_angle = angle + math.pi / 2 + random.uniform(-0.2, 0.2)
                cos_t, sin_t = math.cos(tangent_angle), math.sin(tangent_angle)

                local_box = [[-bw/2, -bh/2], [bw/2, -bh/2], [bw/2, bh/2], [-bw/2, bh/2]]
                b_verts = []
                for lx, ly in local_box:
                    gx = cx + (lx * cos_t - ly * sin_t)
                    gy = cy + (lx * sin_t + ly * cos_t)
                    b_verts.append([round(gx, 2), round(gy, 2)])

                height = round(random.uniform(min_h, max_h), 1)
                mesh_3d = extrude_polygon_to_3d_mesh(b_verts, height)

                buildings.append({
                    "id": f"organic_b_{len(buildings)}",
                    "vertices_2d": b_verts,
                    "height": height,
                    "mesh_3d": mesh_3d,
                    "centroid": [cx, cy, 0.0]
                })

        return buildings

    def _generate_tower_cluster_buildings(self, site_verts, profile, radius, min_h, max_h, street_w, min_gap):
        buildings = []
        num_towers = random.randint(12, 24)

        for i in range(num_towers):
            dist = random.uniform(street_w + 12.0, radius - 10.0)
            angle = random.uniform(0, 2 * math.pi)
            cx = dist * math.cos(angle)
            cy = dist * math.sin(angle)

            bw = random.uniform(28.0, 45.0)
            bh = random.uniform(28.0, 45.0)

            b_verts = [
                [round(cx - bw/2, 2), round(cy - bh/2, 2)],
                [round(cx + bw/2, 2), round(cy - bh/2, 2)],
                [round(cx + bw/2, 2), round(cy + bh/2, 2)],
                [round(cx - bw/2, 2), round(cy + bh/2, 2)],
            ]

            height = round(random.uniform(min_h, max_h), 1)
            mesh_3d = extrude_polygon_to_3d_mesh(b_verts, height)

            buildings.append({
                "id": f"tower_b_{len(buildings)}",
                "vertices_2d": b_verts,
                "height": height,
                "mesh_3d": mesh_3d,
                "centroid": [cx, cy, 0.0]
            })

        return buildings
