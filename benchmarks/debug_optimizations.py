import time
import copy
import hashlib
import json
import math
import sys
from typing import Any, Sequence

import server, geometry as G

def get_layout_hash(trainer: server.ParallelTrainer) -> str:
    """Compute a deterministic hash of all placements across all floors."""
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

def run_suite(patch_fn, name: str, num_episodes: int = 10, tier: str = "XL", max_modules: int = 40):
    patch_fn()
    seeds = [1000 + i * 37 for i in range(num_episodes)]
    total_time = 0.0
    total_steps = 0
    total_placements = 0
    episode_hashes = []
    episode_scores = []
    
    import torch, random
    for ep_idx, seed in enumerate(seeds):
        torch.manual_seed(seed)
        random.seed(seed)
        settings = dict(server.DEFAULT_SETTINGS)
        settings["siteAreaTier"] = tier
        settings["boundaryType"] = "lobed"
        settings["parallelEnvironments"] = 4
        settings["maxModules"] = max_modules
        settings["seed"] = seed
        
        trainer = server.ParallelTrainer(settings=settings)
        trainer.new_site()
        
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
        placements = sum(len(e.placements) for e in trainer.environments)
        total_placements += placements
        h = get_layout_hash(trainer)
        score = float(res.get("metrics", {}).get("score", 0.0) if res else 0.0)
        episode_hashes.append(h)
        episode_scores.append(round(score, 3))
    
    return {
        "name": name,
        "total_time": total_time,
        "avg_ep_time": total_time / num_episodes,
        "avg_step_ms": (total_time / total_steps) * 1000 if total_steps else 0.0,
        "total_steps": total_steps,
        "total_placements": total_placements,
        "hashes": episode_hashes,
        "scores": episode_scores,
    }

orig_step = server.ParallelTrainer.step
orig_room_crossing = server.FloorEnvironment._room_crossing_costs_to_core
orig_place = server.FloorEnvironment.place
orig_reset = server.FloorEnvironment.reset
orig_shared = server.ParallelTrainer._shared_core_stack_candidates

def patch_baseline():
    server.ParallelTrainer.step = orig_step
    server.FloorEnvironment._room_crossing_costs_to_core = orig_room_crossing
    server.FloorEnvironment.place = orig_place
    server.FloorEnvironment.reset = orig_reset
    server.ParallelTrainer._shared_core_stack_candidates = orig_shared

# Strategy 1: Gated Core Search
def patch_s1():
    patch_baseline()
    def fast_shared_core(self, orientation_basis, **kwargs):
        floors = list(self.environments if kwargs.get("environments") is None else kwargs["environments"])
        active_settings = kwargs.get("settings") or self.settings
        if bool(active_settings["singleFloor"]) or len(floors) <= 1:
            return []
        placing_first = all(not env.placements for env in floors)
        if not placing_first:
            primary_site_area = float(floors[0].site["exactArea"]) if floors else 1000.0
            max_cores = server._max_cores_for_site(primary_site_area)
            core_counts = [sum(1 for p in env.placements if p.get("category") == "core") for env in floors]
            if any(count == 0 or count >= max_cores for count in core_counts):
                return []
            room_counts = [sum(1 for p in env.placements if p.get("category") == "room") for env in floors]
            min_current_cores = min(core_counts)
            if any(count < server.SECOND_CORE_MIN_ROOMS * min_current_cores for count in room_counts):
                return []
        return orig_shared(self, orientation_basis, **kwargs)
    server.ParallelTrainer._shared_core_stack_candidates = fast_shared_core

# Strategy 2: Cached Dijkstra Core Distances with proper invalidation
def patch_s2():
    patch_baseline()
    def cached_room_crossing(self, core_ids=None):
        if core_ids is None and hasattr(self, "_cached_room_core_costs") and self._cached_room_core_costs is not None:
            return self._cached_room_core_costs
        val = orig_room_crossing(self, core_ids)
        if core_ids is None:
            self._cached_room_core_costs = val
        return val
    def patched_place(self, candidate, **kwargs):
        self._cached_room_core_costs = None
        return orig_place(self, candidate, **kwargs)
    def patched_reset(self, dictionary):
        self._cached_room_core_costs = None
        return orig_reset(self, dictionary)
        
    server.FloorEnvironment._room_crossing_costs_to_core = cached_room_crossing
    server.FloorEnvironment.place = patched_place
    server.FloorEnvironment.reset = patched_reset

# Strategy 1 + 2 Combined
def patch_s1_s2():
    patch_s1()
    def cached_room_crossing(self, core_ids=None):
        if core_ids is None and hasattr(self, "_cached_room_core_costs") and self._cached_room_core_costs is not None:
            return self._cached_room_core_costs
        val = orig_room_crossing(self, core_ids)
        if core_ids is None:
            self._cached_room_core_costs = val
        return val
    def patched_place(self, candidate, **kwargs):
        self._cached_room_core_costs = None
        return orig_place(self, candidate, **kwargs)
    def patched_reset(self, dictionary):
        self._cached_room_core_costs = None
        return orig_reset(self, dictionary)
        
    server.FloorEnvironment._room_crossing_costs_to_core = cached_room_crossing
    server.FloorEnvironment.place = patched_place
    server.FloorEnvironment.reset = patched_reset

# Strategy 3: Fast Normal Clearance Pre-filter
def patch_s3():
    patch_baseline()
    def fast_edge_alignment(self, module, rotation, include_edge_id=False):
        # Yield valid anchors with normal clearance check
        candidate_poly = rotation["poly"]
        angle_period = int(round(math.pi * server.ATTACHMENT_ANGLE_SCALE))
        poly_len = len(candidate_poly)
        for candidate_index in range(poly_len):
            candidate_first = candidate_poly[candidate_index]
            candidate_second = candidate_poly[(candidate_index + 1) % poly_len]
            candidate_dx = candidate_second["x"] - candidate_first["x"]
            candidate_dy = candidate_second["y"] - candidate_first["y"]
            candidate_length = math.hypot(candidate_dx, candidate_dy)
            if candidate_length < server.MIN_SHARED_EDGE:
                continue
            angle_key = self._attachment_angle_key(candidate_first, candidate_second)
            
            pref_ids = []
            norm_ids = []
            seen_eids = set()
            for delta in (-2, -1, 0, 1, 2):
                lookup = (angle_key + delta) % angle_period
                eids = self.attachment_by_angle.get(lookup)
                if eids:
                    for eid in eids:
                        if eid in seen_eids:
                            continue
                        seen_eids.add(eid)
                        edge = self.attachment_edges.get(eid)
                        if edge is not None:
                            if edge["preferred"]:
                                pref_ids.append(eid)
                            else:
                                norm_ids.append(eid)

            pref_ids.sort(reverse=True)
            norm_ids.sort(reverse=True)
            prioritized = self._sample_attachment_ids(pref_ids + norm_ids)
            for edge_id in prioritized:
                edge = self.attachment_edges[edge_id]
                placed_first = edge["a"]
                placed_second = edge["b"]
                placed_dx = placed_second["x"] - placed_first["x"]
                placed_dy = placed_second["y"] - placed_first["y"]
                placed_length = edge["length"]
                placed_poly = self.placement_by_id[edge["placementId"]]["poly"]
                full_first = placed_poly[edge["edgeIndex"]]
                full_second = placed_poly[(edge["edgeIndex"] + 1) % len(placed_poly)]
                full_placed_length = math.hypot(
                    full_second["x"] - full_first["x"],
                    full_second["y"] - full_first["y"],
                )
                length_ratio = candidate_length / max(full_placed_length, G.EPSILON)
                if not any(abs(length_ratio - valid_ratio) < 5.0e-3 for valid_ratio in (0.5, 1.0, 2.0)):
                    continue
                cross = placed_dx * candidate_dy - placed_dy * candidate_dx
                if abs(cross) > 1.0e-7 * placed_length * candidate_length:
                    continue
                dot = placed_dx * candidate_dx + placed_dy * candidate_dy
                if dot < 0.0:
                    if include_edge_id:
                        yield (placed_second["x"] - candidate_first["x"], placed_second["y"] - candidate_first["y"], edge_id)
                        yield (placed_first["x"] - candidate_second["x"], placed_first["y"] - candidate_second["y"], edge_id)
                    else:
                        yield (placed_second["x"] - candidate_first["x"], placed_second["y"] - candidate_first["y"])
                        yield (placed_first["x"] - candidate_second["x"], placed_first["y"] - candidate_second["y"])
                else:
                    if include_edge_id:
                        yield (placed_first["x"] - candidate_first["x"], placed_first["y"] - candidate_first["y"], edge_id)
                        yield (placed_second["x"] - candidate_second["x"], placed_second["y"] - candidate_second["y"], edge_id)
                    else:
                        yield (placed_first["x"] - candidate_first["x"], placed_first["y"] - candidate_first["y"])
                        yield (placed_second["x"] - candidate_second["x"], placed_second["y"] - candidate_second["y"])
                if include_edge_id:
                    yield ((placed_first["x"] + placed_second["x"] - candidate_first["x"] - candidate_second["x"]) * 0.5,
                           (placed_first["y"] + placed_second["y"] - candidate_first["y"] - candidate_second["y"]) * 0.5, edge_id)
                else:
                    yield ((placed_first["x"] + placed_second["x"] - candidate_first["x"] - candidate_second["x"]) * 0.5,
                           (placed_first["y"] + placed_second["y"] - candidate_first["y"] - candidate_second["y"]) * 0.5)
    server.FloorEnvironment._edge_alignment_anchors = fast_edge_alignment

# Combined patches
def patch_s1_s2():
    patch_s1()
    def cached_room_crossing(self, core_ids=None):
        if core_ids is None and hasattr(self, "_cached_room_core_costs") and self._cached_room_core_costs is not None:
            return self._cached_room_core_costs
        val = orig_room_crossing(self, core_ids)
        if core_ids is None:
            self._cached_room_core_costs = val
        return val
    def patched_place(self, candidate, **kwargs):
        self._cached_room_core_costs = None
        return orig_place(self, candidate, **kwargs)
    def patched_reset(self, dictionary):
        self._cached_room_core_costs = None
        return orig_reset(self, dictionary)
        
    server.FloorEnvironment._room_crossing_costs_to_core = cached_room_crossing
    server.FloorEnvironment.place = patched_place
    server.FloorEnvironment.reset = patched_reset

def patch_s1_s2_s3():
    patch_s1_s2()
    patch_s3()

if __name__ == "__main__":
    print("=" * 90)
    print("BENCHMARKING OPTIMIZATION STRATEGIES ACROSS 10 EPISODES (XL Lobed 4-Floors, 40 maxModules)")
    print("=" * 90)
    
    # 1. Baseline
    b_res = run_suite(patch_baseline, "Baseline (v0.8.0 Current)")
    
    # 2. Strategy 1 (Conditional Core Stack Search)
    s1_res = run_suite(patch_s1, "Strategy 1: Conditional Core Search")
    
    # 3. Strategy 2 (Shortest-Path Core Distance Caching)
    s2_res = run_suite(patch_s2, "Strategy 2: BFS Core Distance Caching")
    
    # 4. Strategy 1 + Strategy 2 Combined
    s12_res = run_suite(patch_s1_s2, "Strategy 1 + 2 Combined")
    
    # 5. Strategy 3 (Clearance Pre-filter)
    s3_res = run_suite(patch_s3, "Strategy 3: Normal Clearance Pre-filter")
    
    # 6. Strategy 1 + 2 + 3 Combined
    s123_res = run_suite(patch_s1_s2_s3, "Strategy 1 + 2 + 3 Combined")

    results = [b_res, s1_res, s2_res, s12_res, s3_res, s123_res]
    
    print("\n" + "=" * 90)
    print(f"{'Strategy / Configuration':<40} | {'Time (10 ep)':<12} | {'Avg/Ep':<10} | {'Speedup':<8} | {'Exact Match':<11}")
    print("-" * 90)
    
    b_time = b_res["total_time"]
    for r in results:
        exact = "YES (100%)" if r["hashes"] == b_res["hashes"] else "NO"
        speedup = f"{b_time / r['total_time']:.2f}x"
        print(f"{r['name']:<40} | {r['total_time']:>9.3f} s | {r['avg_ep_time']:>7.3f} s | {speedup:>8} | {exact:<11}")
    print("=" * 90)

    # Output full summary json
    with open("benchmarks/opt_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nDetailed results saved to benchmarks/opt_results.json")
