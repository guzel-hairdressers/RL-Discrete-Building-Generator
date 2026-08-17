import json
import math

def generate_ascii_plots():
    with open("benchmarks/convergence_750_any_results.json", "r") as f:
        data = json.load(f)

    mlp_scores = data["v084_mlp"]["scores"]
    se2_scores = data["v085_se2"]["scores"]
    mlp_fills = [f * 100.0 for f in data["v084_mlp"]["fills"]]
    se2_fills = [f * 100.0 for f in data["v085_se2"]["fills"]]

    # Rolling average window = 30
    def rolling_avg(arr, w=30):
        out = []
        for i in range(len(arr)):
            start = max(0, i - w + 1)
            window = arr[start:i+1]
            out.append(sum(window) / len(window))
        return out

    mlp_sc_smooth = rolling_avg(mlp_scores)
    se2_sc_smooth = rolling_avg(se2_scores)
    mlp_fl_smooth = rolling_avg(mlp_fills)
    se2_fl_smooth = rolling_avg(se2_fills)

    width = 75
    height = 18

    def plot_curve(y1_arr, y2_arr, title, y_label, y_min_val, y_max_val, y_unit):
        grid = [[' ' for _ in range(width)] for _ in range(height)]
        
        # Sample 75 points across the 750 episodes
        indices = [int(i * (len(y1_arr) - 1) / (width - 1)) for i in range(width)]
        
        for col, idx in enumerate(indices):
            v1 = y1_arr[idx]
            v2 = y2_arr[idx]
            
            row1 = int((v1 - y_min_val) / (y_max_val - y_min_val) * (height - 1))
            row2 = int((v2 - y_min_val) / (y_max_val - y_min_val) * (height - 1))
            
            row1 = max(0, min(height - 1, row1))
            row2 = max(0, min(height - 1, row2))
            
            # Note: invert row for display (top = row 0)
            r1 = height - 1 - row1
            r2 = height - 1 - row2
            
            grid[r1][col] = '·' # MLP
            grid[r2][col] = '█' # SE(2)
            if r1 == r2:
                grid[r1][col] = '◆'

        out_lines = []
        out_lines.append(f"\n┌─ {title} " + "─" * (width + 12 - len(title)))
        out_lines.append(f"│ Legend: [█] v0.8.5 SE(2) Transformer (Smooth) | [·] v0.8.4 MLP Baseline (Smooth)")
        out_lines.append("├" + "─" * (width + 14))
        
        for r in range(height):
            val = y_max_val - (r / (height - 1)) * (y_max_val - y_min_val)
            prefix = f"│ {val:5.1f}{y_unit} ┤ "
            row_str = "".join(grid[r])
            out_lines.append(prefix + row_str)
            
        out_lines.append("│        └" + "─" * width)
        out_lines.append("│ Episode: 1" + " " * (width // 2 - 12) + "Ep 375" + " " * (width // 2 - 10) + "Ep 750")
        out_lines.append("└" + "─" * (width + 14))
        return "\n".join(out_lines)

    p1 = plot_curve(mlp_sc_smooth, se2_sc_smooth, "OVERLAYED GRAPH 1: ARCHITECTURAL SCORE (pts) VS EPISODES (1-750)", "Score", 20.0, 80.0, "pts")
    p2 = plot_curve(mlp_fl_smooth, se2_fl_smooth, "OVERLAYED GRAPH 2: FLOOR FILL RATIO (%) VS EPISODES (1-750)", "Fill", 25.0, 60.0, "%  ")
    
    print(p1)
    print(p2)

if __name__ == "__main__":
    generate_ascii_plots()
