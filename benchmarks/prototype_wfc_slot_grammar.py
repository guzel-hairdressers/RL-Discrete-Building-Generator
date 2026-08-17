import time
import math
import collections
import server
import geometry as G

def analyze_mathematical_slot_reduction():
    print("=" * 90)
    print("MATHEMATICAL FRONTIER REDUCTION & WFC SLOT PROTOTYPE TEST")
    print("=" * 90)
    
    settings = dict(server.DEFAULT_SETTINGS)
    settings["siteAreaTier"] = "XL"
    settings["boundaryType"] = "lobed"
    settings["parallelEnvironments"] = 4
    settings["maxModules"] = 120
    settings["seed"] = 1000
    
    trainer = server.ParallelTrainer(settings=settings)
    trainer.new_site()
    
    env = trainer.environments[0]
    palette = trainer.dictionary
    
    # Step 1: Advance building to 40 modules to create a realistic complex perimeter
    for step in range(40):
        cands = env.generate_candidates(settings, limit=12)
        if not cands:
            break
        env.place(cands[0])
        
    print(f"Building State at Step 40:")
    print(f" - Placements count: {len(env.placements)}")
    print(f" - Total exterior attachment edges: {len(env.attachment_edges)}")
    
    # Step 2: Measure Naive Combinatorial Search Space
    n_shapes = len(palette)
    total_rotations = sum(len(m["rotations"]) for m in palette)
    total_module_edges = sum(len(rot["poly"]) for m in palette for rot in m["rotations"])
    naive_combinations = len(env.attachment_edges) * total_module_edges
    
    print(f"\n[1] Naive Combinatorial Search Space:")
    print(f" - Shapes in Palette: {n_shapes} (Total Rotations: {total_rotations})")
    print(f" - Candidate Shape Edges: {total_module_edges}")
    print(f" - Naive Pairwise Checks: {len(env.attachment_edges)} building edges × {total_module_edges} shape edges = {naive_combinations:,} combinations!")

    # Step 3: Build Inverted Normal & Length Pre-Indexed Table
    t0 = time.perf_counter()
    slot_index = collections.defaultdict(list)
    angle_period = int(round(math.pi * server.ATTACHMENT_ANGLE_SCALE))
    
    for mod_idx, module in enumerate(palette):
        for rot_idx, rot in enumerate(module["rotations"]):
            poly = rot["poly"]
            p_len = len(poly)
            for e_idx in range(p_len):
                p1 = poly[e_idx]
                p2 = poly[(e_idx + 1) % p_len]
                dx = p2["x"] - p1["x"]
                dy = p2["y"] - p1["y"]
                e_len = round(math.hypot(dx, dy), 2)
                angle_key = env._attachment_angle_key(p1, p2)
                # Store entry indexed by (angle_key, quantized length)
                slot_index[(angle_key, e_len)].append({
                    "moduleId": module["id"],
                    "module": module,
                    "rotation": rot,
                    "edgeIndex": e_idx,
                    "p1": p1,
                    "p2": p2,
                    "length": e_len,
                })
    t_index = time.perf_counter() - t0
    print(f"\n[2] Inverted Slot Index Built in {t_index*1000:.2f} ms:")
    print(f" - Total Discrete (Angle, Length) Buckets: {len(slot_index)}")

    # Step 4: Evaluate Slots on Current Building Perimeter
    t0 = time.perf_counter()
    slot_matches = 0
    entropy_dist = collections.Counter()
    valid_candidates = []
    
    for eid, edge in env.attachment_edges.items():
        p1 = edge["a"]
        p2 = edge["b"]
        dx = p2["x"] - p1["x"]
        dy = p2["y"] - p1["y"]
        e_len = round(edge["length"], 2)
        edge_angle_key = env._attachment_angle_key(p1, p2)
        
        # Invert angle key for opposite/antiparallel normal
        opposite_angle_key = (edge_angle_key + angle_period // 2) % angle_period
        
        # Query discrete index directly in O(1)
        matched_tiles = []
        for delta in (-1, 0, 1):
            k = ((opposite_angle_key + delta) % angle_period, e_len)
            matched_tiles.extend(slot_index.get(k, []))
            
        slot_matches += len(matched_tiles)
        entropy = len(matched_tiles)
        entropy_dist[entropy] += 1
        
        # Verify valid placement for matched tiles
        for tile in matched_tiles:
            anchor_x = p2["x"] - tile["p1"]["x"]
            anchor_y = p2["y"] - tile["p1"]["y"]
            cand = env._candidate_from_anchor(
                tile["module"],
                tile["rotation"],
                anchor_x,
                anchor_y,
                settings,
                0.0,
                {},
            )
            if cand is not None:
                valid_candidates.append(cand)
                
    t_eval = time.perf_counter() - t0
    
    print(f"\n[3] Inverted Geometric Slot Evaluation:")
    print(f" - Total Tests Generated: {slot_matches} (vs {naive_combinations:,} naive tests -> {naive_combinations/slot_matches:.1f}x reduction!)")
    print(f" - Valid Non-Overlapping Legal Actions Found: {len(valid_candidates)}")
    print(f" - Evaluation Time for ALL Slots across Entire Building: {t_eval*1000:.2f} ms")
    print(f" - Slot Entropy Distribution across Building Perimeter:")
    for ent, count in sorted(entropy_dist.items()):
        print(f"    * Slots with {ent} compatible shape options: {count} slots")
        
    print("\n" + "=" * 90)
    print("MATHEMATICAL CONCLUSION:")
    print(f"1. Search Space Reduction: {naive_combinations:,} -> {slot_matches} tests ({naive_combinations/slot_matches:.1f}x reduction).")
    print(f"2. Full Policy Coverage: Evaluates all {len(valid_candidates)} legal actions across the entire building in under {t_eval*1000:.1f} ms!")
    print("=" * 90)

if __name__ == "__main__":
    analyze_mathematical_slot_reduction()
