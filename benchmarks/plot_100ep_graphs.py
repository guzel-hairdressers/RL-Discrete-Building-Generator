import json

def plot_100ep_ascii_graphs():
    with open("benchmarks/benchmark_100ep_results.json") as f:
        data = json.load(f)
        
    episodes = data["episodes"]
    v085_scores = data["v085_scores"]
    phase1i_scores = data["phase1i_scores"]
    v085_fills = [f * 100 for f in data["v085_fills"]]
    phase1i_fills = [f * 100 for f in data["phase1i_fills"]]
    
    # 1. Overlayed Score Graph
    print("=" * 115)
    print("1. OVERLAYED ARCHITECTURAL SCORE (PTS) vs EPISODES (1 TO 100)")
    print("   [#] = Phase 1I Hierarchical WFC (Avg: 94.27 pts)")
    print("   [.] = v0.8.5 Baseline (Avg: 39.73 pts)")
    print("=" * 115)
    
    # Downsample to 20 buckets of 5 episodes each for ASCII clarity
    b_scores_bucket = [sum(v085_scores[i:i+5])/5 for i in range(0, 100, 5)]
    p_scores_bucket = [sum(phase1i_scores[i:i+5])/5 for i in range(0, 100, 5)]
    
    y_min, y_max = 20, 100
    height = 16
    for h in range(height, -1, -1):
        val = y_min + (y_max - y_min) * (h / height)
        line = f"{val:5.1f} | "
        for b in range(20):
            bs = b_scores_bucket[b]
            ps = p_scores_bucket[b]
            b_cell = int(round((bs - y_min) / (y_max - y_min) * height))
            p_cell = int(round((ps - y_min) / (y_max - y_min) * height))
            
            if p_cell == h and b_cell == h:
                line += " * "
            elif p_cell == h:
                line += " # "
            elif b_cell == h:
                line += " . "
            else:
                line += "   "
        print(line)
    print("      +-" + "---" * 20)
    print("      | " + " ".join(f"{i:2d}" for i in range(5, 105, 5)) + " (Episode)")
    
    # 2. Overlayed Fill Ratio Graph
    print("\n" + "=" * 115)
    print("2. OVERLAYED FLOOR FILL RATIO (%) vs EPISODES (1 TO 100)")
    print("   [#] = Phase 1I Hierarchical WFC (Avg: 94.7%)")
    print("   [.] = v0.8.5 Baseline (Avg: 38.3%)")
    print("=" * 115)
    
    b_fills_bucket = [sum(v085_fills[i:i+5])/5 for i in range(0, 100, 5)]
    p_fills_bucket = [sum(phase1i_fills[i:i+5])/5 for i in range(0, 100, 5)]
    
    y_min, y_max = 20, 100
    for h in range(height, -1, -1):
        val = y_min + (y_max - y_min) * (h / height)
        line = f"{val:5.1f}%| "
        for b in range(20):
            bf = b_fills_bucket[b]
            pf = p_fills_bucket[b]
            b_cell = int(round((bf - y_min) / (y_max - y_min) * height))
            p_cell = int(round((pf - y_min) / (y_max - y_min) * height))
            
            if p_cell == h and b_cell == h:
                line += " * "
            elif p_cell == h:
                line += " # "
            elif b_cell == h:
                line += " . "
            else:
                line += "   "
        print(line)
    print("      +-" + "---" * 20)
    print("      | " + " ".join(f"{i:2d}" for i in range(5, 105, 5)) + " (Episode)")
    print("=" * 115)

if __name__ == "__main__":
    plot_100ep_ascii_graphs()
