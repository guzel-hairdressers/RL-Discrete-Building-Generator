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

# Baseline functions
orig_gen = server.FloorEnvironment.generate_candidates
orig_place = server.FloorEnvironment.place
orig_reset = server.FloorEnvironment.reset

# Build Inverted Slot Index for a dictionary
def build_slot_index(dictionary):
    slot_index = collections.defaultdict(list)
    angle_period = int(round(math.pi * server.ATTACHMENT_ANGLE_SCALE))
    for module in dictionary:
        for rotation in module["rotations"]:
            poly = rotation["poly"]
            p_len = len(poly)
            if "_c_poly_array" not in rotation:
                sig = G._native_polygon_signature(poly)
                rotation["_c_poly_array"] = G._packed_polygon_from_signature(sig)
                rotation["_c_poly_count"] = len(sig)
                
            for e_idx in range(p_len):
                p1 = poly[e_idx]
                p2 = poly[(e_idx + 1) % p_len]
                dx = p2["x"] - p1["x"]
                dy = p2["y"] - p1["y"]
                e_len = round(math.hypot(dx, dy), 4)
                if e_len < server.MIN_SHARED_EDGE:
                    continue
                angle = math.atan2(dy, dx)
                angle_key = int(round(angle * server.ATTACHMENT_ANGLE_SCALE)) % angle_period
                
                # Corner interior angles
                prev_p = poly[(e_idx - 1) % p_len]
                next_p = poly[(e_idx + 2) % p_len]
                # Corner angle at p1
                v1_in = (p1["x"] - prev_p["x"], p1["y"] - prev_p["y"])
                v1_out = (p2["x"] - p1["x"], p2["y"] - p1["y"])
                # Corner angle at p2
                v2_in = (p2["x"] - p1["x"], p2["y"] - p1["y"])
                v2_out = (next_p["x"] - p2["x"], next_p["y"] - p2["y"])
                
                slot_index[(angle_key, e_len)].append({
                    "module": module,
                    "rotation": rotation,
                    "edgeIndex": e_idx,
                    "p1": p1,
                    "p2": p2,
                    "length": e_len,
                })
    return slot_index

# Subphase Generator Factory
def make_slot_grammar_generator(
    enable_wedge_filter: bool = False,
    enable_depth_filter: bool = False,
    enable_hop_filter: bool = False,
    enable_wfc_autocollapse: bool = False,
    uncapped_pool: bool = False,
):
    def slot_generate_candidates(
        self,
        settings: dict,
        orientation_basis: float = 0.0,
        limit: int = 12,
        profiler: Any = None,
        allow_core: bool = True,
    ):
        placing_first = not self.placements
        if placing_first:
            return orig_gen(self, settings, orientation_basis, limit, profiler, allow_core)
            
        if not hasattr(self, "_slot_index") or self._slot_index is None:
            self._slot_index = build_slot_index(self.dictionary)
            
        angle_period = int(round(math.pi * server.ATTACHMENT_ANGLE_SCALE))
        single_floor = bool(settings["singleFloor"])
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
        cat_limit = 9999 if uncapped_pool else max(8, int(limit))
        core_candidates = []
        room_candidates = []
        seen = set()
        max_hops = int(settings.get("maxRoomHops", 5))
        
        # Edge-driven search over building perimeter
        pref_edges = []
        norm_edges = []
        for eid, edge in self.attachment_edges.items():
            if edge.get("preferred"):
                pref_edges.append(edge)
            else:
                norm_edges.append(edge)
        all_edges = pref_edges + norm_edges
        
        for edge in all_edges:
            parent_id = edge["placementId"]
            parent_placement = self.placement_by_id.get(parent_id)
            if parent_placement is None:
                continue
                
            # Hop filter
            if enable_hop_filter and "room" in allowed_cats:
                parent_cost = room_core_costs.get(parent_id, 0)
                if self.core_ids and parent_cost >= max_hops:
                    edge_allowed_cats = [c for c in allowed_cats if c == "core"]
                else:
                    edge_allowed_cats = allowed_cats
            else:
                edge_allowed_cats = allowed_cats
                
            if not edge_allowed_cats:
                continue
                
            p1 = edge["a"]
            p2 = edge["b"]
            dx = p2["x"] - p1["x"]
            dy = p2["y"] - p1["y"]
            e_len = round(edge["length"], 4)
            edge_angle = math.atan2(dy, dx)
            edge_angle_key = int(round(edge_angle * server.ATTACHMENT_ANGLE_SCALE)) % angle_period
            
            # Antiparallel normal angle
            opp_angle_key = (edge_angle_key + angle_period // 2) % angle_period
            
            # Direct O(1) slot index lookup for matching lengths
            matched_tiles = []
            # Check length matches (1.0x, 0.5x, 2.0x)
            for delta in (-1, 0, 1):
                k = ((opp_angle_key + delta) % angle_period, e_len)
                matched_tiles.extend(self._slot_index.get(k, ()))
                
            for tile in matched_tiles:
                module = tile["module"]
                rotation = tile["rotation"]
                mod_id = module["id"]
                
                # Anchor calculations
                anchor_x = p2["x"] - tile["p1"]["x"]
                anchor_y = p2["y"] - tile["p1"]["y"]
                
                for category in edge_allowed_cats:
                    if category == "core" and float(module["area"]) + 1.0e-8 < 24.0:
                        continue
                    sig = (mod_id, category, round(float(rotation.get("angle", 0.0)), 6), round(anchor_x, 4), round(anchor_y, 4))
                    if sig in seen:
                        continue
                    seen.add(sig)
                    
                    cand = self._candidate_from_anchor(
                        module,
                        rotation,
                        anchor_x,
                        anchor_y,
                        settings,
                        orientation_basis,
                        room_core_costs,
                        placement_category=category,
                    )
                    if cand is None:
                        continue
                        
                    if category == "core":
                        core_candidates.append(cand)
                    else:
                        room_candidates.append(cand)
                        
                    if not uncapped_pool:
                        if len(core_candidates) >= cat_limit and len(room_candidates) >= cat_limit:
                            return core_candidates + room_candidates
                            
        return core_candidates + room_candidates
    return slot_generate_candidates

Any = object

def run_subphase_suite(gen_fn, name: str, num_episodes: int = 10, max_modules: int = 120):
    server.FloorEnvironment.generate_candidates = gen_fn
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
        for env in trainer.environments:
            env._slot_index = build_slot_index(trainer.dictionary)
            
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
    print("=" * 105)
    print("RUNNING PHASE 1E SUBPHASE PROGRESSION BENCHMARK (120 PLACEMENTS/FLOOR, 10 EPISODES, XL LOBED)")
    print("=" * 105)
    
    # 0. Baseline
    base_fn = orig_gen
    base = run_subphase_suite(base_fn, "Baseline (v0.8.0 Current)", num_episodes=10, max_modules=120)
    print(f"[Done] {base['name']}: {base['total_time']:.2f}s ({base['avg_ep_time']:.2f}s/ep)")
    
    # 1. Phase 1E.1: Inverted (Normal, Length) Compatibility Index
    p1e1_fn = make_slot_grammar_generator()
    p1e1 = run_subphase_suite(p1e1_fn, "+ Phase 1E.1: Inverted (Normal, Length) Index", num_episodes=10, max_modules=120)
    print(f"[Done] {p1e1['name']}: {p1e1['total_time']:.2f}s ({p1e1['avg_ep_time']:.2f}s/ep)")
    
    # 2. Phase 1E.2: Inverted Index + Hop Horizon Gating
    p1e2_fn = make_slot_grammar_generator(enable_hop_filter=True)
    p1e2 = run_subphase_suite(p1e2_fn, "+ Phase 1E.2: Core Hop Horizon Gating", num_episodes=10, max_modules=120)
    print(f"[Done] {p1e2['name']}: {p1e2['total_time']:.2f}s ({p1e2['avg_ep_time']:.2f}s/ep)")

    # 3. Phase 1E.6: Full-Action Uncapped Policy Evaluation
    p1e6_fn = make_slot_grammar_generator(enable_hop_filter=True, uncapped_pool=True)
    p1e6 = run_subphase_suite(p1e6_fn, "+ Phase 1E.6: Full-Action Policy Coverage (Uncapped)", num_episodes=10, max_modules=120)
    print(f"[Done] {p1e6['name']}: {p1e6['total_time']:.2f}s ({p1e6['avg_ep_time']:.2f}s/ep)")

    results = [base, p1e1, p1e2, p1e6]
    
    print("\n" + "=" * 105)
    print(f"{'Subphase / Configuration':<45} | {'Time (10 ep)':<12} | {'Avg/Ep':<10} | {'Speedup':<8} | {'Exact Match':<11}")
    print("-" * 105)
    base_time = base["total_time"]
    for r in results:
        exact = "YES (100%)" if r["hashes"] == base["hashes"] else "NO"
        speedup = f"{base_time / r['total_time']:.2f}x"
        print(f"{r['name']:<45} | {r['total_time']:>9.2f} s | {r['avg_ep_time']:>7.2f} s | {speedup:>8} | {exact:<11}")
    print("=" * 105)
    
    with open("benchmarks/phase1e_results.json", "w") as f:
        json.dump(results, f, indent=2)
