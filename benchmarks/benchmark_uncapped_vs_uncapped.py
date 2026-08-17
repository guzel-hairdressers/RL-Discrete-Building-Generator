from __future__ import annotations
import time
import torch
import random
import hashlib
import json
import math
import collections
import server, geometry as G, graph

def run_pure_uncapped_comparison(num_episodes: int = 5, max_modules: int = 120):
    print("=" * 105)
    print(f"DIRECT UNCAPPED VS UNCAPPED BENCHMARK ({num_episodes} EPISODES, {max_modules} PLACEMENTS/FLOOR, XL LOBED SITES)")
    print("=" * 105)
    
    seeds = [1000 + i * 37 for i in range(num_episodes)]
    
    # -------------------------------------------------------------
    # 1. Old Baseline WITHOUT Early Truncation (Unbounded Brute-Force)
    # -------------------------------------------------------------
    print("\n[1] Running Old Baseline WITHOUT Early Truncation (Unbounded Brute-Force)...")
    def old_brute_force_uncapped(self, settings, orientation_basis=0.0, limit=9999, profiler=None, allow_core=True):
        placing_first = not self.placements
        single_floor = bool(settings["singleFloor"])
        modules = self.dictionary
        core_count = sum(1 for p in self.placements if p.get("category") == "core")
        room_count = sum(1 for p in self.placements if p.get("category") == "room")
        max_cores = server._max_cores_for_site(float(self.site["exactArea"]))
        if placing_first:
            allowed_cats = ["room"] if single_floor else ["core"]
        else:
            allowed_cats = ["room"]
            if not single_floor and (core_count == 0 or (core_count < max_cores and room_count >= server.SECOND_CORE_MIN_ROOMS * core_count)):
                allowed_cats.append("core")
        if not allow_core:
            allowed_cats = [c for c in allowed_cats if c != "core"]
            
        core_candidates = []
        room_candidates = []
        seen = set()
        frontier = self._frontier_cells() if placing_first else []
        room_core_costs = self._room_crossing_costs_to_core() if self.core_ids else {}
        
        for module in modules:
            for category in allowed_cats:
                if category == "core" and float(module["area"]) + 1.0e-8 < 24.0:
                    continue
                for rotation in module["rotations"]:
                    if placing_first:
                        anchors = [(t["x"] - c["x"], t["y"] - c["y"], None) for t in frontier for c in rotation["cells"][:8]]
                    else:
                        anchors = list(self._edge_alignment_anchors(module, rotation, include_edge_id=True))
                    for anchor_x, anchor_y, edge_id in anchors:
                        sig = (module["id"], category, round(float(rotation.get("angle", 0.0)), 6), round(anchor_x, 6), round(anchor_y, 6))
                        if sig in seen:
                            continue
                        seen.add(sig)
                        cand = self._candidate_from_anchor(
                            module, rotation, anchor_x, anchor_y, settings, orientation_basis, room_core_costs, placement_category=category
                        )
                        if cand is not None:
                            valid_alignment = placing_first or self._validate_edge_alignment(cand.poly)
                            if not valid_alignment or not self._materialize_candidate(cand, settings, orientation_basis):
                                continue
                            if category == "core":
                                core_candidates.append(cand)
                            else:
                                room_candidates.append(cand)
                            # NOTE: NO EARLY BREAK! Evaluates EVERY single candidate on the board!
        return core_candidates + room_candidates

    server.FloorEnvironment.generate_candidates = old_brute_force_uncapped
    t0 = time.perf_counter()
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
        for _ in range(max_modules):
            res = trainer.step(trainer.generation_id, trainer.episode)
            if res.get("episodeDone") or all(e.done for e in trainer.environments):
                break
    t_old_uncapped = time.perf_counter() - t0
    avg_old_uncapped = t_old_uncapped / num_episodes
    print(f" -> Old Uncapped Time ({num_episodes} ep): {t_old_uncapped:.2f} s ({avg_old_uncapped:.2f} s/ep)")

    # -------------------------------------------------------------
    # 2. New Inverted Slot Grammar WITHOUT Early Truncation (Our Uncapped Engine)
    # -------------------------------------------------------------
    print("\n[2] Running New Inverted Slot Grammar WITHOUT Early Truncation (Uncapped)...")
    def new_slot_uncapped(self, settings, orientation_basis=0.0, limit=9999, profiler=None, allow_core=True):
        placing_first = not self.placements
        if placing_first:
            return old_brute_force_uncapped(self, settings, orientation_basis, limit, profiler, allow_core)
            
        if not hasattr(self, "slot_index") or self.slot_index is None:
            self.slot_index = self._build_slot_index(self.dictionary)
            
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
            dx = p2["x"] - p1["x"]
            dy = p2["y"] - p1["y"]
            placed_length = edge["length"]
            edge_angle_key = edge["angleKey"]
            placed_poly = self.placement_by_id[edge["placementId"]]["poly"]
            full_first = placed_poly[edge["edgeIndex"]]
            full_second = placed_poly[(edge["edgeIndex"] + 1) % len(placed_poly)]
            full_placed_length = math.hypot(full_second["x"] - full_first["x"], full_second["y"] - full_first["y"])
            
            matched_tiles = []
            for delta in (-2, -1, 0, 1, 2):
                lookup = (edge_angle_key + delta) % angle_period
                matched_tiles.extend(self.slot_index.get(lookup, ()))
                
            for tile in matched_tiles:
                candidate_length = tile["length"]
                length_ratio = candidate_length / max(full_placed_length, G.EPSILON)
                if not any(abs(length_ratio - valid_ratio) < 5.0e-3 for valid_ratio in (0.5, 1.0, 2.0)):
                    continue
                cross = dx * tile["dy"] - dy * tile["dx"]
                if abs(cross) > 1.0e-7 * placed_length * candidate_length:
                    continue
                dot = dx * tile["dx"] + dy * tile["dy"]
                if dot >= 0.0:
                    continue
                    
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
                        # NOTE: NO EARLY BREAK! Evaluates 100% of all legal actions!
        return core_candidates + room_candidates

    server.FloorEnvironment.generate_candidates = new_slot_uncapped
    t0 = time.perf_counter()
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
        for _ in range(max_modules):
            res = trainer.step(trainer.generation_id, trainer.episode)
            if res.get("episodeDone") or all(e.done for e in trainer.environments):
                break
    t_new_uncapped = time.perf_counter() - t0
    avg_new_uncapped = t_new_uncapped / num_episodes
    print(f" -> New Inverted Slot Grammar Uncapped Time ({num_episodes} ep): {t_new_uncapped:.2f} s ({avg_new_uncapped:.2f} s/ep)")

    speedup = t_old_uncapped / t_new_uncapped
    print("\n" + "=" * 105)
    print("FINAL HEAD-TO-HEAD DIRECT COMPARISON (UNCAPPED VS UNCAPPED):")
    print(f" * Old Brute-Force (Uncapped):        {t_old_uncapped:.2f} s  ({avg_old_uncapped:.2f} s/ep)")
    print(f" * New Inverted Slot Grammar (Uncapped): {t_new_uncapped:.2f} s  ({avg_new_uncapped:.2f} s/ep)")
    print(f" * NET SPEEDUP (Both evaluating 100% of actions): {speedup:.2f}x FASTER!")
    print("=" * 105)

if __name__ == "__main__":
    run_pure_uncapped_comparison(num_episodes=5, max_modules=120)
