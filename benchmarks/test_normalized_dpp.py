import torch
import math

def compute_dpp_diversity_bonus(embeddings, sigma=0.5, eps=1.0e-3):
    N = len(embeddings)
    if N < 2:
        return 0.0
    feat_tensor = torch.tensor(embeddings, dtype=torch.float32)
    diff = feat_tensor.unsqueeze(1) - feat_tensor.unsqueeze(0)
    dist_sq = (diff ** 2).sum(dim=-1)
    S = torch.exp(-dist_sq / (2.0 * (sigma ** 2)))
    S_reg = S + torch.eye(N) * eps

    sign, logdet = torch.linalg.slogdet(S_reg)
    if sign.item() <= 0:
        return 0.0

    min_logdet = math.log(N + eps) + (N - 1) * math.log(eps)
    raw_logdet = float(logdet.item())
    diversity_nats = max(0.0, (raw_logdet - min_logdet) / N)
    return float(diversity_nats)

# Test 1: Identical embeddings (Mode Collapse)
identical_emb = [[0.25, 0.85, 0.50, 0.33, 0.40] for _ in range(5)]
d_collapse = compute_dpp_diversity_bonus(identical_emb)

# Test 2: Highly diverse embeddings (Orthogonal Typologies)
diverse_emb = [
    [0.10, 0.90, 0.20, 0.10, 0.10], # Linear Spine
    [0.45, 0.75, 0.80, 0.50, 0.80], # Courtyard Atrium
    [0.30, 0.85, 0.40, 0.90, 0.60], # Radial Cluster
    [0.50, 0.70, 0.90, 0.20, 0.30], # Dense Block
    [0.20, 0.95, 0.30, 0.40, 0.50], # Perimeter Ring
]
d_diverse = compute_dpp_diversity_bonus(diverse_emb)

print(f"Test 1 (Identical Mode Collapse): {d_collapse:.4f} nats (Expected 0.0000)")
print(f"Test 2 (Diverse Typologies):      {d_diverse:.4f} nats (Expected > 4.5000)")
print(f"Net DPP Diversity Volume Gain:    {d_diverse - d_collapse:+.4f} nats")
