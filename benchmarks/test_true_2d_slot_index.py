from __future__ import annotations
import time
import torch
import random
import math
import collections
import server, geometry as G

def test_true_2d_slot_index(num_episodes=10, max_modules=120):
    print("=" * 105)
    print(f"BENCHMARKING TRUE 2D (ANTIPARALLEL ANGLE, LENGTH) SLOT INDEX ON 120 MODULES/FLOOR")
    print("=" * 105)
    
    seeds = [100 + i * 23 for i in range(num_episodes)]
    
    # 1. True 2D Slot Index Builder
    def build_true_2d_slot_index(dictionary: list[dict]):
        angle_period = int(round(math.pi * server.ATTACHMENT_ANGLE_SCALE))
        slot_index = collections.defaultdict(list)
        for module in dictionary:
            for rotation in module["rotations"]:
                poly = rotation["poly"]
                p_len = len(poly)
                for e_idx in range(p_len):
                    p1 = poly[e_idx]
                    p2 = poly[(e_idx + 1) % p_len]
                    dx = p2["x"] - p1["x"]
                    dy = p2["y"] - p1["y"]
                    e_len = round(math.hypot(dx, dy), 3)
                    if e_len < server.MIN_SHARED_EDGE:
                        continue
                    angle = math.atan2(dy, dx)
                    angle_key = int(round(angle * server.ATTACHMENT_ANGLE_SCALE)) % angle_period
                    quantized_len = round(e_len, 2)
                    slot_index[(angle_key, quantized_len)].append({
                        "module": module,
                        "rotation": rotation,
                        "edgeIndex": e_idx,
                        "p1": p1,
                        "p2": p2,
                        "dx": dx,
                        "dy": dy,
                        "length": e_len,
                    })
        return dict(slot_index)

    # 2. Ultra-Fast 2D Direct Lookup Generator
    def ultra_fast_2d_generate_candidates(self, settings, orientation_basis=0.0, limit=9999, profiler=None, allow_core=True):
        placing_first = not self.placements
        if placing_first:
            return orig_gen(self, settings, orientation_basis, limit, profiler, allow_core)
            
        if not hasattr(self, "_slot_index_2d") or self._slot_index_2d is None:
            self._slot_index_2d = build_true_2d_slot_index(self.dictionary)
            
        angle_period = int(round(math.pi * server.ATTACHMENT_ANGLE_SCALE))
        single_floor = bool(settings["singleFloor"])
        core_count = sum(1 for p in self.placements if p.get("category") == "core")
        room_count = sum(1 for p in self.placements if p.get("category") == "room")
        max_cores = server._max_cores_for_site(float(self.site["exactArea"]))
        allowed_cats = ["room"]
        if not single_floor and (core_count == 0 or (core_count < max_cores and room_count >= server.SECOND_CORE_MIN_ROOMS * core_count)):
            allowed_cats.append("core")
        if not allow_core:
            allowed_cats = [c for c in allowed_cats if c != "core"]
            
        room_core_costs = self._room_crossing_costs_to_core() if self.core_ids else {}
        core_candidates = []
        room_candidates = []
        seen = set()
        max_hops = int(settings.get("maxRoomHops", 5))
        
        pref_ids = [eid for eid, e in self.attachment_edges.items() if e.get("preferred")]
        norm_ids = [eid for eid, e in self.attachment_edges.items() if not e.get("preferred")]
        all_edge_ids = pref_ids + norm_ids
        
        for edge_id in all_edge_ids:
            edge = self.attachment_edges.get(edge_id)
            if edge is None:
                continue
            parent_id = edge["placementId"]
            parent_cost = room_core_costs.get(parent_id, 0)
            if self.core_ids and parent_cost >= max_hops:
                edge_allowed_cats = [c for c in allowed_cats if c == "core"]
            else:
                edge_allowed_cats = allowed_cats
            if not edge_allowed_cats:
                continue
                
            p1 = edge["a"]
            p2 = edge["b"]
            edge_angle_key = edge["angleKey"]
            placed_poly = self.placement_by_id[edge["placementId"]]["poly"]
            full_first = placed_poly[edge["edgeIndex"]]
            full_second = placed_poly[(edge["edgeIndex"] + 1) % len(placed_poly)]
            full_placed_length = round(math.hypot(full_second["x"] - full_first["x"], full_second["y"] - full_first["y"]), 2)
            
            # Direct Antiparallel & Length Lookups (0.5x, 1.0x, 2.0x)
            compatible_lengths = (
                round(full_placed_length * 0.5, 2),
                full_placed_length,
                round(full_placed_length * 2.0, 2)
            )
            
            matched_tiles = []
            for delta in (-1, 0, 1):
                lookup_angle = (edge_angle_key + delta) % angle_period
                for comp_len in compatible_lengths:
                    tiles = self._slot_index_2d.get((lookup_angle, comp_len))
                    if tiles:
                        matched_tiles.extend(tiles)
                        
            for tile in matched_tiles:
                module = tile["module"]
                rotation = tile["rotation"]
                mod_id = module["id"]
                candidate_first = tile["p1"]
                candidate_second = tile["p2"]
                
                for anchor_x, anchor_y in (
                    (p2["x"] - candidate_first["x"], p2["y"] - candidate_first["y"]),
                    (p1["x"] - candidate_second["x"], p1["y"] - candidate_second["y"]),
                ):
                    for category in edge_allowed_cats:
                        if category == "core" and float(module["area"]) + 1.0e-8 < 24.0:
                            continue
                        sig = (mod_id, category, round(float(rotation.get("angle", 0.0)), 6), round(anchor_x, 6), round(anchor_y, 6))
                        if sig in seen:
                            continue
                        seen.add(sig)
                        cand = self._candidate_from_anchor(
                            module, rotation, anchor_x, anchor_y, settings, orientation_basis, room_core_costs, placement_category=category
                        )
                        if cand is None:
                            continue
                        valid_alignment = self._validate_edge_alignment(cand.poly)
                        if not valid_alignment or not self._materialize_candidate(cand, settings, orientation_basis):
                            continue
                        if category == "core":
                            core_candidates.append(cand)
                        else:
                            room_candidates.append(cand)
        return core_candidates + room_candidates

    orig_gen = server.FloorEnvironment.generate_candidates
    server.FloorEnvironment.generate_candidates = ultra_fast_2d_generate_candidates
    
    times = []
    scores = []
    fills = []
    
    for ep_idx, seed in enumerate(seeds):
        torch.manual_seed(seed)
        random.seed(seed)
        settings = dict(server.DEFAULT_SETTINGS)
        settings["siteAreaTier"] = "XL"
        settings["boundaryType"] = "lobed"
        settings["parallelEnvironments"] = 4
        settings["maxModules"] = max_modules
        settings["seed"] = seed
        
        t0 = time.perf_counter()
        trainer = server.ParallelTrainer(settings=settings)
        trainer.new_site()
        for _ in range(max_modules):
            res = trainer.step(trainer.generation_id, trainer.episode)
            if res.get("episodeDone") or all(e.done for e in trainer.environments):
                break
        ep_duration = time.perf_counter() - t0
        times.append(ep_duration)
        metrics = res.get("metrics", {})
        scores.append(float(metrics.get("score", 0.0)))
        fills.append(float(metrics.get("fillRatio", 0.0)))
        print(f" Ep {ep_idx+1:02d} (Seed {seed:4d}): Time = {ep_duration:5.2f}s | Score = {scores[-1]:5.2f} | Fill = {fills[-1]*100:4.1f}%")
        
    print("-" * 105)
    print(f"Mean Episode Time (120 modules / 4 floors): {sum(times)/len(times):.2f} s / ep  (Total: {sum(times):.2f} s)")
    print("=" * 105)

if __name__ == "__main__":
    test_true_2d_slot_index(num_episodes=10, max_modules=120)
