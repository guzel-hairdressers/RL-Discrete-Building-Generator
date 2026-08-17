import torch
import numpy as np
import math

def compute_dpp_diversity(feature_matrix: np.ndarray, quality_scores: np.ndarray, sigma: float = 1.0) -> float:
    """Compute log det(L) for a batch of generated layouts."""
    n = len(feature_matrix)
    # Compute RBF similarity matrix
    diff = feature_matrix[:, np.newaxis, :] - feature_matrix[np.newaxis, :, :]
    dist_sq = np.sum(diff ** 2, axis=-1)
    S = np.exp(-dist_sq / (2.0 * sigma ** 2))
    
    # Scale by quality scores q_i = exp(R_i / scale)
    q = np.exp(quality_scores / 100.0)
    L = np.outer(q, q) * S
    
    # Add small diagonal jitter for numerical stability
    L += np.eye(n) * 1e-4
    
    # Compute log det(L) via Cholesky or SVD
    sign, logdet = np.linalg.slogdet(L)
    return float(logdet) if sign > 0 else -999.0

if __name__ == "__main__":
    print("=" * 90)
    print("PHASE 1G: DETERMINANTAL POINT PROCESS (DPP) TYPOLOGICAL DIVERSITY TEST")
    print("=" * 90)
    
    # Case A: Homogeneous / Collapsed Batch (5 identical or near-identical layouts)
    # Features: [daylight_ratio, circulation_compactness, area_fill, atrium_openness, bpe_vocab_entropy]
    collapsed_batch = np.array([
        [0.72, 0.81, 0.65, 0.10, 0.45],
        [0.72, 0.82, 0.65, 0.10, 0.44],
        [0.71, 0.81, 0.66, 0.11, 0.45],
        [0.73, 0.80, 0.65, 0.10, 0.46],
        [0.72, 0.81, 0.65, 0.10, 0.45],
    ])
    scores_a = np.array([85.0, 85.2, 84.8, 85.5, 85.1])
    logdet_a = compute_dpp_diversity(collapsed_batch, scores_a)
    
    # Case B: Diverse Batch (5 structurally distinct architectural typologies)
    # 1: Central Courtyard Atrium, 2: Linear Spine, 3: Radial Cluster, 4: Split Wing, 5: Perimeter Ring
    diverse_batch = np.array([
        [0.88, 0.70, 0.62, 0.45, 0.78], # Courtyard Atrium
        [0.65, 0.92, 0.75, 0.05, 0.55], # Linear Spine
        [0.82, 0.85, 0.68, 0.20, 0.85], # Radial Cluster
        [0.75, 0.65, 0.58, 0.35, 0.62], # Split Wing
        [0.91, 0.78, 0.60, 0.50, 0.70], # Perimeter Ring
    ])
    scores_b = np.array([86.0, 88.5, 85.0, 84.0, 87.2])
    logdet_b = compute_dpp_diversity(diverse_batch, scores_b)
    
    print(f"Evaluation of Batch Diversity via DPP Log-Determinant:")
    print(f" - Collapsed Homogeneous Batch Log-Det: {logdet_a:.2f}")
    print(f" - Diverse Typologies Batch Log-Det:     {logdet_b:.2f}")
    print(f" - Net Determinantal Volume Gain:       +{logdet_b - logdet_a:.2f} nats!")
    print("\nMathematical Interpretation:")
    print(" * Maximizing log det(L) forces the RL policy to discover structurally orthogonal typologies")
    print("   while maintaining high individual multi-objective quality scores.")
    print("=" * 90)
