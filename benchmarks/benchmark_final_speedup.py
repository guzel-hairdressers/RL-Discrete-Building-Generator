from __future__ import annotations
import time
import torch
import random
import hashlib
import json
import math
import collections
import ctypes
import server, geometry as G, graph

def get_layout_hash(trainer: server.ParallelTrainer) -> str:
    records = []
    for env in trainer.environments:
        floor_recs = []
        for p in env.placements:
            poly_coords = [(round(pt["x"], 4), round(pt["y"], 4)) for pt in p["poly"]]
            floor_recs.append({
                "id": p["id"],
                "mid": p.get("moduleId", ""),
                "cat": p.get("category", "room"),
                "poly": poly_coords,
            })
        records.append(floor_recs)
    return hashlib.sha256(json.dumps(records, sort_keys=True).encode("utf-8")).hexdigest()[:12]

# Save baseline functions
orig_gen = server.FloorEnvironment.generate_candidates
orig_place = server.FloorEnvironment.place
orig_reset = server.FloorEnvironment.reset
orig_remove_att = server.FloorEnvironment._remove_attachment
orig_cand_anchor = server.FloorEnvironment._candidate_from_anchor

# Pre-cache C arrays for module rotations
def ensure_c_arrays(dictionary):
    for module in dictionary:
        for rot in module["rotations"]:
            if "_c_poly_array" not in rot:
                sig = G._native_polygon_signature(rot["poly"])
                rot["_c_poly_array"] = G._packed_polygon_from_signature(sig)
                rot["_c_poly_count"] = len(sig)

# Native Direct Array SAT in candidate_from_anchor
def native_direct_candidate_from_anchor(
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
):
    rotation_bounds = rotation.get("bounds")
    if rotation_bounds is None:
        rotation_bounds = G.bounds_of(rotation["poly"])
        rotation["bounds"] = rotation_bounds
    bounds = {
        "minX": rotation_bounds["minX"] + anchor_x,
        "maxX": rotation_bounds["maxX"] + anchor_x,
        "minY": rotation_bounds["minY"] + anchor_y,
        "maxY": rotation_bounds["maxY"] + anchor_y,
    }
    site_bounds = self.site["bounds"]
    if (
        bounds["minX"] < site_bounds["minX"] - server.SPATIAL_PADDING
        or bounds["maxX"] > site_bounds["maxX"] + server.SPATIAL_PADDING
        or bounds["minY"] < site_bounds["minY"] - server.SPATIAL_PADDING
        or bounds["maxY"] > site_bounds["maxY"] + server.SPATIAL_PADDING
    ):
        return None
        
    t_overlap = time.perf_counter()
    has_overlap = False
    if self.placements:
        if "_c_poly_array" not in rotation:
            sig = G._native_polygon_signature(rotation["poly"])
            rotation["_c_poly_array"] = G._packed_polygon_from_signature(sig)
            rotation["_c_poly_count"] = len(sig)
        nearby_ids = {
            identifier
            for identifier in self._nearby_placement_ids(bounds)
            if self._bounds_intersect(bounds, self.placement_bounds[identifier])
        }
        for identifier in nearby_ids:
            p = self.placement_by_id[identifier]
            if "_c_poly_array" not in p:
                sig = G._native_polygon_signature(p["poly"])
                p["_c_poly_array"] = G._packed_polygon_from_signature(sig)
                p["_c_poly_count"] = len(sig)
            if G._libfast_geo.polygons_overlap_translated_c(
                rotation["_c_poly_array"],
                rotation["_c_poly_count"],
                ctypes.c_double(anchor_x),
                ctypes.c_double(anchor_y),
                p["_c_poly_array"],
                p["_c_poly_count"],
            ):
                has_overlap = True
                break

    if cg_sub_totals is not None:
        cg_sub_totals["cgOverlapCollisions"] += time.perf_counter() - t_overlap
    if has_overlap:
        return None
        
    # Delegate remaining rare valid candidate materialization to standard path
    return orig_cand_anchor(
        self, module, rotation, anchor_x, anchor_y, settings, orientation_basis, room_core_costs, placement_category, cg_sub_totals
    )

# Saturated Edge Invalidation
def make_dormant_edge_patches():
    def dormant_place(self, candidate, **kwargs):
        res = orig_place(self, candidate, **kwargs)
        if hasattr(self, "_dormant_edges") and self._dormant_edges:
            poly = candidate.poly if hasattr(candidate, "poly") else candidate["poly"]
            pb = G.bounds_of(poly)
            to_wake = []
            for edge_id in list(self._dormant_edges):
                edge = self.attachment_edges.get(edge_id)
                if edge is None:
                    to_wake.append(edge_id)
                else:
                    mid_x = (edge["a"]["x"] + edge["b"]["x"]) * 0.5
                    mid_y = (edge["a"]["y"] + edge["b"]["y"]) * 0.5
                    if (
                        pb["minX"] - 18.0 <= mid_x <= pb["maxX"] + 18.0
                        and pb["minY"] - 18.0 <= mid_y <= pb["maxY"] + 18.0
                    ):
                        to_wake.append(edge_id)
            for e_id in to_wake:
                self._dormant_edges.discard(e_id)
        return res

    def dormant_reset(self, dictionary):
        self._dormant_edges = set()
        ensure_c_arrays(dictionary)
        return orig_reset(self, dictionary)

    def dormant_remove_attachment(self, edge_id: int):
        if hasattr(self, "_dormant_edges"):
            self._dormant_edges.discard(edge_id)
        return orig_remove_att(self, edge_id)

    def dormant_generate_candidates(
        self,
        settings: dict,
        orientation_basis: float = 0.0,
        limit: int = 12,
        profiler: Any = None,
        allow_core: bool = True,
    ):
        if not hasattr(self, "_dormant_edges"):
            self._dormant_edges = set()
            
        placing_first = not self.placements
        if placing_first:
            return orig_gen(self, settings, orientation_basis, limit, profiler, allow_core)
            
        # Fast path: filter out anchors from dormant edges
        tested_edges = set()
        successful_edges = set()
        
        single_floor = bool(settings["singleFloor"])
        modules = self.rng.shuffle(self.dictionary)
        core_count = sum(1 for p in self.placements if p.get("category") == "core")
        room_count = sum(1 for p in self.placements if p.get("category") == "room")
        max_cores = server._max_cores_for_site(float(self.site["exactArea"]))
        
        allowed_cats = ["room"]
        min_rooms_for_next_core = server.SECOND_CORE_MIN_ROOMS * core_count
        if not single_floor and (
            core_count == 0
            or (core_count < max_cores and room_count >= min_rooms_for_next_core)
        ):
            allowed_cats.append("core")
        if not allow_core:
            allowed_cats = [c for c in allowed_cats if c != "core"]
            
        room_core_costs = self._room_crossing_costs_to_core() if self.core_ids else {}
        cat_limit = max(8, int(limit))
        core_candidates = []
        room_candidates = []
        seen = set()
        early_break = False
        cg_sub_totals = {
            "cgAnchorSearch": 0.0,
            "cgOverlapCollisions": 0.0,
            "cgSiteBoundary": 0.0,
            "cgNeighborAnalysis": 0.0,
            "cgEdgeAlignment": 0.0,
            "cgFeatureExtraction": 0.0,
        }
        
        for module in modules:
            rotations = self.rng.shuffle(module["rotations"])
            for category in allowed_cats:
                if category == "core" and float(module["area"]) + 1.0e-8 < 24.0:
                    continue
                for rotation in rotations:
                    raw_anchors = list(self._edge_alignment_anchors(module, rotation, include_edge_id=True))
                    anchors = [
                        (ax, ay, eid) for ax, ay, eid in raw_anchors
                        if eid is None or eid not in self._dormant_edges
                    ]
                    for anchor_x, anchor_y, edge_id in anchors:
                        if edge_id is not None:
                            tested_edges.add(edge_id)
                        signature = (
                            module["id"],
                            category,
                            round(float(rotation.get("angle", 0.0)), 6),
                            round(float(anchor_x), 4),
                            round(float(anchor_y), 4),
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
                        if candidate is None:
                            continue
                        if edge_id is not None:
                            successful_edges.add(edge_id)
                            
                        if category == "core":
                            core_candidates.append(candidate)
                        else:
                            room_candidates.append(candidate)
                        if len(core_candidates) >= cat_limit and len(room_candidates) >= cat_limit:
                            early_break = True
                            break
                    if early_break:
                        break
                if early_break:
                    break
            if early_break:
                break
                
        for edge_id in tested_edges:
            if edge_id not in successful_edges:
                self._dormant_edges.add(edge_id)
                
        all_candidates = core_candidates + room_candidates
        if not all_candidates and self._dormant_edges:
            self._dormant_edges.clear()
            return orig_gen(self, settings, orientation_basis, limit, profiler, allow_core)
        return all_candidates

    return dormant_place, dormant_reset, dormant_remove_attachment, dormant_generate_candidates

Any = object
dorm_place, dorm_reset, dorm_remove_att, dorm_gen = make_dormant_edge_patches()

def configure_mode(mode: str):
    if mode == "p1_p3":
        server.FloorEnvironment.place = orig_place
        server.FloorEnvironment.reset = orig_reset
        server.FloorEnvironment._remove_attachment = orig_remove_att
        server.FloorEnvironment.generate_candidates = orig_gen
        server.FloorEnvironment._candidate_from_anchor = orig_cand_anchor
    elif mode == "native_sat":
        server.FloorEnvironment.place = orig_place
        server.FloorEnvironment.reset = orig_reset
        server.FloorEnvironment._remove_attachment = orig_remove_att
        server.FloorEnvironment.generate_candidates = orig_gen
        server.FloorEnvironment._candidate_from_anchor = native_direct_candidate_from_anchor
    elif mode == "dormant_edges":
        server.FloorEnvironment.place = dorm_place
        server.FloorEnvironment.reset = dorm_reset
        server.FloorEnvironment._remove_attachment = dorm_remove_att
        server.FloorEnvironment.generate_candidates = dorm_gen
        server.FloorEnvironment._candidate_from_anchor = orig_cand_anchor
    elif mode == "combined":
        server.FloorEnvironment.place = dorm_place
        server.FloorEnvironment.reset = dorm_reset
        server.FloorEnvironment._remove_attachment = dorm_remove_att
        server.FloorEnvironment.generate_candidates = dorm_gen
        server.FloorEnvironment._candidate_from_anchor = native_direct_candidate_from_anchor

def run_suite(mode: str, name: str, num_episodes: int = 10, max_modules: int = 120):
    configure_mode(mode)
    seeds = [1000 + i * 37 for i in range(num_episodes)]
    total_time = 0.0
    total_steps = 0
    hashes = []
    scores = []
    
    for seed in seeds:
        torch.manual_seed(seed)
        random.seed(seed)
        settings = dict(server.DEFAULT_SETTINGS)
        settings["siteAreaTier"] = "XL"
        settings["boundaryType"] = "lobed"
        settings["parallelEnvironments"] = 4
        settings["maxModules"] = max_modules
        settings["seed"] = seed
        
        trainer = server.ParallelTrainer(settings=settings)
        trainer.new_site()
        ensure_c_arrays(trainer.dictionary)
        
        t0 = time.perf_counter()
        steps = 0
        while steps < max_modules:
            res = trainer.step(trainer.generation_id, trainer.episode)
            steps += 1
            if res.get("episodeDone") or all(e.done for e in trainer.environments):
                break
        t1 = time.perf_counter()
        
        total_time += (t1 - t0)
        total_steps += steps
        h = get_layout_hash(trainer)
        score = float(res.get("metrics", {}).get("score", 0.0) if res else 0.0)
        hashes.append(h)
        scores.append(round(score, 3))
    
    return {
        "name": name,
        "total_time": total_time,
        "avg_ep_time": total_time / num_episodes,
        "avg_step_ms": (total_time / total_steps) * 1000 if total_steps else 0.0,
        "total_steps": total_steps,
        "hashes": hashes,
        "scores": scores,
    }

if __name__ == "__main__":
    print("=" * 100)
    print("FINAL BENCHMARK SUITE (120 PLACEMENTS / FLOOR, 10 EPISODES, XL LOBED)")
    print("=" * 100)
    
    # 1. Phase 1 + 3 Reference
    p13 = run_suite("p1_p3", "Phase 1+3: Kernel + Wall Pruning", num_episodes=10, max_modules=120)
    print(f"[Done] {p13['name']}: {p13['total_time']:.2f}s ({p13['avg_ep_time']:.2f}s/ep)")
    
    # 2. Phase 1+3 + Native Direct SAT
    sat = run_suite("native_sat", "+ Native Direct Array SAT", num_episodes=10, max_modules=120)
    print(f"[Done] {sat['name']}: {sat['total_time']:.2f}s ({sat['avg_ep_time']:.2f}s/ep)")
    
    # 3. Phase 1+3 + Saturated Edge Invalidation
    dorm = run_suite("dormant_edges", "+ Saturated Edge Invalidation", num_episodes=10, max_modules=120)
    print(f"[Done] {dorm['name']}: {dorm['total_time']:.2f}s ({dorm['avg_ep_time']:.2f}s/ep)")

    # 4. Combined: Phase 1+3 + Native SAT + Saturated Edges
    comb = run_suite("combined", "+ Saturated Edges + Native SAT (Combined)", num_episodes=10, max_modules=120)
    print(f"[Done] {comb['name']}: {comb['total_time']:.2f}s ({comb['avg_ep_time']:.2f}s/ep)")

    results = [p13, sat, dorm, comb]
    
    print("\n" + "=" * 100)
    print(f"{'Configuration':<45} | {'Time (10 ep)':<12} | {'Avg/Ep':<10} | {'Speedup':<8} | {'Exact Match':<11}")
    print("-" * 100)
    base_time = 152.26  # Authoritative Baseline recorded earlier
    for r in results:
        exact = "YES (100%)" if r["hashes"] == p13["hashes"] else "NO"
        speedup = f"{base_time / r['total_time']:.2f}x"
        print(f"{r['name']:<45} | {r['total_time']:>9.2f} s | {r['avg_ep_time']:>7.2f} s | {speedup:>8} | {exact:<11}")
    print("=" * 100)
    
    with open("benchmarks/final_speedup_results.json", "w") as f:
        json.dump(results, f, indent=2)
