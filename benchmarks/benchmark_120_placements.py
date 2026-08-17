import time
import torch
import random
import hashlib
import json
import math
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

# --- OPTIMIZATION PATCHES ---

# 1. Fast exposed_wall_segments with AABB spatial pruning
def fast_exposed_wall_segments(polygons):
    result = []
    poly_bounds = [G.bounds_of(p) for p in polygons]
    n = len(polygons)
    for polygon_index in range(n):
        poly = polygons[polygon_index]
        pb = poly_bounds[polygon_index]
        for edge_index, first in enumerate(poly):
            second = poly[(edge_index + 1) % len(poly)]
            eb_minX = min(first["x"], second["x"]) - G.COLLINEAR_EPSILON
            eb_maxX = max(first["x"], second["x"]) + G.COLLINEAR_EPSILON
            eb_minY = min(first["y"], second["y"]) - G.COLLINEAR_EPSILON
            eb_maxY = max(first["y"], second["y"]) + G.COLLINEAR_EPSILON
            
            intervals = []
            for other_index in range(n):
                if other_index == polygon_index:
                    continue
                ob = poly_bounds[other_index]
                if (
                    eb_maxX < ob["minX"] - 0.01
                    or ob["maxX"] < eb_minX - 0.01
                    or eb_maxY < ob["minY"] - 0.01
                    or ob["maxY"] < eb_minY - 0.01
                ):
                    continue
                other_poly = polygons[other_index]
                for other_edge_index, third in enumerate(other_poly):
                    fourth = other_poly[(other_edge_index + 1) % len(other_poly)]
                    interval = G._overlap_interval_on_first(first, second, third, fourth)
                    if interval is not None:
                        intervals.append(interval)
            intervals.sort()
            merged = []
            for start, end in intervals:
                if not merged or start > merged[-1][1] + G.COLLINEAR_EPSILON:
                    merged.append([start, end])
                else:
                    merged[-1][1] = max(merged[-1][1], end)
            cursor = 0.0
            complements = []
            for start, end in merged:
                if start > cursor + G.COLLINEAR_EPSILON:
                    complements.append((cursor, start))
                cursor = max(cursor, end)
            if cursor < 1.0 - G.COLLINEAR_EPSILON:
                complements.append((cursor, 1.0))
            if not merged:
                complements = [(0.0, 1.0)]
            for start, end in complements:
                exposed_first = G._point(
                    first["x"] + (second["x"] - first["x"]) * start,
                    first["y"] + (second["y"] - first["y"]) * start,
                )
                exposed_second = G._point(
                    first["x"] + (second["x"] - first["x"]) * end,
                    first["y"] + (second["y"] - first["y"]) * end,
                )
                length = G._distance(exposed_first, exposed_second)
                if length > G.COLLINEAR_EPSILON:
                    result.append({
                        "a": exposed_first,
                        "b": exposed_second,
                        "length": length,
                        "polygonIndex": polygon_index,
                        "edgeIndex": edge_index,
                    })
    return result

# 2. Fast find_edge_connections with edge AABB pruning in BPE
def fast_find_edge_connections(g: graph.LayoutGraph) -> list[graph.EdgeConnection]:
    connections = []
    pids = list(g.nodes.keys())
    n = len(pids)
    node_bounds = {pid: G.bounds_of(g.nodes[pid]["poly"]) for pid in pids}
    
    for i in range(n):
        pid_a = pids[i]
        node_a = g.nodes[pid_a]
        poly_a = node_a["poly"]
        n_a = len(poly_a)
        bounds_a = node_bounds[pid_a]
        
        for j in range(i + 1, n):
            pid_b = pids[j]
            bounds_b = node_bounds[pid_b]
            if (
                bounds_a["maxX"] < bounds_b["minX"] - 0.2
                or bounds_b["maxX"] < bounds_a["minX"] - 0.2
                or bounds_a["maxY"] < bounds_b["minY"] - 0.2
                or bounds_b["maxY"] < bounds_a["minY"] - 0.2
            ):
                continue
            node_b = g.nodes[pid_b]
            poly_b = node_b["poly"]
            n_b = len(poly_b)
            
            best_conn = None
            best_overlap_len = 0.0
            
            for ea in range(n_a):
                a1 = poly_a[ea]
                a2 = poly_a[(ea + 1) % n_a]
                ea_minX = min(a1["x"], a2["x"]) - 0.2
                ea_maxX = max(a1["x"], a2["x"]) + 0.2
                ea_minY = min(a1["y"], a2["y"]) - 0.2
                ea_maxY = max(a1["y"], a2["y"]) + 0.2
                len_a = G._distance(a1, a2)
                if len_a < 1e-5:
                    continue
                    
                for eb in range(n_b):
                    b1 = poly_b[eb]
                    b2 = poly_b[(eb + 1) % n_b]
                    if (
                        ea_maxX < min(b1["x"], b2["x"])
                        or max(b1["x"], b2["x"]) < ea_minX
                        or ea_maxY < min(b1["y"], b2["y"])
                        or max(b1["y"], b2["y"]) < ea_minY
                    ):
                        continue
                    len_b = G._distance(b1, b2)
                    if len_b < 1e-5:
                        continue
                    
                    overlap_measure = graph._symmetric_overlap_measure(a1, a2, b1, b2)
                    if overlap_measure is not None:
                        (t_start, t_end), _, overlap_abs_len = overlap_measure
                        min_edge_len = min(len_a, len_b)
                        if (
                            overlap_abs_len + 1.0e-12 >= graph.BPE_MIN_OVERLAP_FRACTION * min_edge_len
                            and overlap_abs_len > best_overlap_len
                        ):
                            dx = a2["x"] - a1["x"]
                            dy = a2["y"] - a1["y"]
                            ov_start = {"x": a1["x"] + t_start * dx, "y": a1["y"] + t_start * dy}
                            ov_end = {"x": a1["x"] + t_end * dx, "y": a1["y"] + t_end * dy}
                            best_conn = graph.EdgeConnection(
                                shape_id_a=pid_a,
                                shape_id_b=pid_b,
                                edge_idx_a=ea,
                                edge_idx_b=eb,
                                overlap_start=ov_start,
                                overlap_end=ov_end,
                                overlap_fraction_a=overlap_abs_len / len_a,
                                overlap_fraction_b=overlap_abs_len / len_b,
                            )
                            best_overlap_len = overlap_abs_len
            if best_conn is not None:
                connections.append(best_conn)
    return connections

# 3. Fast Gated Core Search
orig_shared = server.ParallelTrainer._shared_core_stack_candidates
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

orig_exposed = G.exposed_wall_segments
orig_find_edges = graph.find_edge_connections

def apply_optimizations(enable: bool):
    if enable:
        G.exposed_wall_segments = fast_exposed_wall_segments
        graph.find_edge_connections = fast_find_edge_connections
        server.ParallelTrainer._shared_core_stack_candidates = fast_shared_core
    else:
        G.exposed_wall_segments = orig_exposed
        graph.find_edge_connections = orig_find_edges
        server.ParallelTrainer._shared_core_stack_candidates = orig_shared

def run_suite(optimized: bool, name: str, num_episodes: int = 10, max_modules: int = 120):
    apply_optimizations(optimized)
    seeds = [1000 + i * 37 for i in range(num_episodes)]
    total_time = 0.0
    total_steps = 0
    total_placements = 0
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
        hashes.append(h)
        scores.append(round(score, 3))
    
    return {
        "name": name,
        "total_time": total_time,
        "avg_ep_time": total_time / num_episodes,
        "avg_step_ms": (total_time / total_steps) * 1000 if total_steps else 0.0,
        "total_steps": total_steps,
        "total_placements": total_placements,
        "hashes": hashes,
        "scores": scores,
    }

if __name__ == "__main__":
    print("=" * 95)
    print("BENCHMARKING 120 PLACEMENTS PER FLOOR ACROSS 10 EPISODES (XL Lobed 4-Floors)")
    print("=" * 95)
    
    print("\nRunning Baseline (10 episodes @ 120 maxModules)...")
    base = run_suite(optimized=False, name="Baseline (v0.8.0 Current)", num_episodes=10, max_modules=120)
    print(f"Baseline Done: {base['total_time']:.2f}s total ({base['avg_ep_time']:.2f}s/ep)")
    
    print("\nRunning Optimized Suite (10 episodes @ 120 maxModules)...")
    opt = run_suite(optimized=True, name="Optimized Kernel & Graph Suite", num_episodes=10, max_modules=120)
    print(f"Optimized Done: {opt['total_time']:.2f}s total ({opt['avg_ep_time']:.2f}s/ep)")
    
    exact = "YES (100%)" if base["hashes"] == opt["hashes"] else "NO"
    speedup = base["total_time"] / opt["total_time"]
    
    print("\n" + "=" * 95)
    print(f"{'Configuration':<35} | {'Time (10 ep)':<12} | {'Avg/Ep':<10} | {'Speedup':<8} | {'Exact Match':<11}")
    print("-" * 95)
    print(f"{base['name']:<35} | {base['total_time']:>9.2f} s | {base['avg_ep_time']:>7.2f} s | {'1.00x':>8} | {'YES (100%)':<11}")
    print(f"{opt['name']:<35} | {opt['total_time']:>9.2f} s | {opt['avg_ep_time']:>7.2f} s | {speedup:>7.2f}x | {exact:<11}")
    print("=" * 95)
    
    with open("benchmarks/results_120.json", "w") as f:
        json.dump([base, opt], f, indent=2)
