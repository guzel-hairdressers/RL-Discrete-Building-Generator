import time
import torch
import random
import hashlib
import json
import math
import collections
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

# Save original functions
orig_native_overlap = G._native_symmetric_segment_overlap_values
orig_extract_graph = graph.extract_layout_graph
orig_exposed = G.exposed_wall_segments
orig_find_edges = graph.find_edge_connections
orig_shared = server.ParallelTrainer._shared_core_stack_candidates

# --- OPTIMIZATION 1: Thread-Safe Unlocked Direct Segment Overlap ---
def fast_native_symmetric_segment_overlap_values(
    first_x: float, first_y: float,
    second_x: float, second_y: float,
    third_x: float, third_y: float,
    fourth_x: float, fourth_y: float,
    linear_tolerance: float,
    angular_tolerance: float,
):
    dx1 = second_x - first_x
    dy1 = second_y - first_y
    dx2 = fourth_x - third_x
    dy2 = fourth_y - third_y
    first_len_sq = dx1 * dx1 + dy1 * dy1
    second_len_sq = dx2 * dx2 + dy2 * dy2
    if first_len_sq <= 1.0e-10 or second_len_sq <= 1.0e-10:
        return None
    cross = abs(dx1 * dy2 - dy1 * dx2)
    if cross * cross > angular_tolerance * angular_tolerance * first_len_sq * second_len_sq:
        return None
    return orig_native_overlap.__wrapped__(
        first_x, first_y, second_x, second_y, third_x, third_y, fourth_x, fourth_y, linear_tolerance, angular_tolerance
    )

# --- OPTIMIZATION 2: Spatial Port Grid for extract_layout_graph ---
def fast_extract_layout_graph(placements: list[dict], playground_id: int = 0) -> graph.LayoutGraph:
    nodes = {p["id"]: p for p in placements}
    connections = []
    if not placements:
        return graph.LayoutGraph(nodes=nodes, connections=connections, playground_id=playground_id)
        
    all_ports = {pid: graph.assign_ports(p) for pid, p in nodes.items()}
    node_bounds = {pid: G.bounds_of(nodes[pid]["poly"]) for pid in nodes}
    
    # Spatial hashing on 10m grid buckets for port pairs
    grid = collections.defaultdict(list)
    cell_size = 10.0
    for pid, b in node_bounds.items():
        min_gx = int(math.floor((b["minX"] - 0.5) / cell_size))
        max_gx = int(math.floor((b["maxX"] + 0.5) / cell_size))
        min_gy = int(math.floor((b["minY"] - 0.5) / cell_size))
        max_gy = int(math.floor((b["maxY"] + 0.5) / cell_size))
        for gx in range(min_gx, max_gx + 1):
            for gy in range(min_gy, max_gy + 1):
                grid[(gx, gy)].append(pid)
                
    tested_pairs = set()
    for pids_in_cell in grid.values():
        if len(pids_in_cell) <= 1:
            continue
        n_c = len(pids_in_cell)
        for i in range(n_c):
            pid_a = pids_in_cell[i]
            for j in range(i + 1, n_c):
                pid_b = pids_in_cell[j]
                pair_id = (pid_a, pid_b) if pid_a < pid_b else (pid_b, pid_a)
                if pair_id in tested_pairs:
                    continue
                tested_pairs.add(pair_id)
                
                bounds_a = node_bounds[pair_id[0]]
                bounds_b = node_bounds[pair_id[1]]
                if (
                    bounds_a["maxX"] < bounds_b["minX"] - 0.5
                    or bounds_b["maxX"] < bounds_a["minX"] - 0.5
                    or bounds_a["maxY"] < bounds_b["minY"] - 0.5
                    or bounds_b["maxY"] < bounds_a["minY"] - 0.5
                ):
                    continue
                    
                ports_a = all_ports[pair_id[0]]
                ports_b = all_ports[pair_id[1]]
                for pa in ports_a:
                    for pb in ports_b:
                        overlap_measure = graph._symmetric_overlap_measure(
                            pa.start, pa.end, pb.end, pb.start
                        )
                        if overlap_measure is not None:
                            (start, end), _, shared_length = overlap_measure
                            port_a_length = graph.distance(pa.start, pa.end)
                            port_b_length = graph.distance(pb.start, pb.end)
                            shorter_length = min(port_a_length, port_b_length)
                            if shared_length + 1.0e-12 >= graph.BPE_MIN_OVERLAP_FRACTION * shorter_length:
                                dx = pa.end["x"] - pa.start["x"]
                                dy = pa.end["y"] - pa.start["y"]
                                overlap_start = {
                                    "x": pa.start["x"] + start * dx,
                                    "y": pa.start["y"] + start * dy
                                }
                                overlap_end = {
                                    "x": pa.start["x"] + end * dx,
                                    "y": pa.start["y"] + end * dy
                                }
                                connections.append(graph.PortConnection(
                                    port_a=pa,
                                    port_b=pb,
                                    overlap_segment=(overlap_start, overlap_end)
                                ))
    return graph.LayoutGraph(nodes=nodes, connections=connections, playground_id=playground_id)

# --- OPTIMIZATION 3: AABB Spatial Pruning in exposed_wall_segments ---
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

# --- OPTIMIZATION 4: Gated Multi-Floor Core Alignment ---
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

def set_opt_state(opt1=False, opt2=False, opt3=False, opt4=False):
    G._native_symmetric_segment_overlap_values = fast_native_symmetric_segment_overlap_values if opt1 else orig_native_overlap
    graph.extract_layout_graph = fast_extract_layout_graph if opt2 else orig_extract_graph
    G.exposed_wall_segments = fast_exposed_wall_segments if opt3 else orig_exposed
    server.ParallelTrainer._shared_core_stack_candidates = fast_shared_core if opt4 else orig_shared

def run_suite(name: str, opt1=False, opt2=False, opt3=False, opt4=False, num_episodes: int = 10, max_modules: int = 120):
    set_opt_state(opt1, opt2, opt3, opt4)
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
        "hashes": hashes,
        "scores": scores,
    }

if __name__ == "__main__":
    print("=" * 95)
    print("RUNNING ACROSS-PHASE PROGRESSION (120 PLACEMENTS / FLOOR, 10 EPISODES, XL LOBED)")
    print("=" * 95)
    
    # 1. Baseline
    b = run_suite("Baseline (v0.8.0)", opt1=False, opt2=False, opt3=False, opt4=False)
    print(f"[Done] {b['name']}: {b['total_time']:.2f}s ({b['avg_ep_time']:.2f}s/ep)")
    
    # 2. Phase 1 (Thread-Lock Removal on Overlap Kernel)
    p1 = run_suite("+ Phase 1: Unlocked Segment Kernel", opt1=True, opt2=False, opt3=False, opt4=False)
    print(f"[Done] {p1['name']}: {p1['total_time']:.2f}s ({p1['avg_ep_time']:.2f}s/ep)")
    
    # 3. Phase 1 + 2 (Spatial Port Grid)
    p2 = run_suite("+ Phase 2: Spatial Port Grid", opt1=True, opt2=True, opt3=False, opt4=False)
    print(f"[Done] {p2['name']}: {p2['total_time']:.2f}s ({p2['avg_ep_time']:.2f}s/ep)")
    
    # 4. Phase 1 + 2 + 3 (Wall Spatial Pruning)
    p3 = run_suite("+ Phase 3: Spatial Wall Pruning", opt1=True, opt2=True, opt3=True, opt4=False)
    print(f"[Done] {p3['name']}: {p3['total_time']:.2f}s ({p3['avg_ep_time']:.2f}s/ep)")
    
    # 5. Phase 1 + 2 + 3 + 4 (Gated Core Search)
    p4 = run_suite("+ Phase 4: Gated Multi-Floor Cores", opt1=True, opt2=True, opt3=True, opt4=True)
    print(f"[Done] {p4['name']}: {p4['total_time']:.2f}s ({p4['avg_ep_time']:.2f}s/ep)")

    results = [b, p1, p2, p3, p4]
    
    print("\n" + "=" * 95)
    print(f"{'Phase / Configuration':<36} | {'Time (10 ep)':<12} | {'Avg/Ep':<10} | {'Speedup':<8} | {'Exact Match':<11}")
    print("-" * 95)
    b_time = b["total_time"]
    for r in results:
        exact = "YES (100%)" if r["hashes"] == b["hashes"] else "NO"
        speedup = f"{b_time / r['total_time']:.2f}x"
        print(f"{r['name']:<36} | {r['total_time']:>9.2f} s | {r['avg_ep_time']:>7.2f} s | {speedup:>8} | {exact:<11}")
    print("=" * 95)
    
    with open("benchmarks/speedup_3x_results.json", "w") as f:
        json.dump(results, f, indent=2)
