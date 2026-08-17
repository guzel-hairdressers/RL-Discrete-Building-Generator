#!/usr/bin/env python3
import unittest
import math
import torch
import server

class TestEquivariantPolicy(unittest.TestCase):
    """Validate SE(2) Euclidean Rotation/Translation Invariance of PolicyModel."""

    def setUp(self):
        torch.manual_seed(42)
        self.model = server.PolicyModel()
        self.model.eval()

    def test_translation_invariance(self):
        """Logits must be strictly invariant when all candidate coordinates are translated."""
        K = 12
        features = torch.randn(K, server.PLACEMENT_FEATURE_DIM)
        positions = torch.randn(K, 2) * 20.0
        angles = torch.rand(K) * 2.0 * math.pi

        with torch.no_grad():
            base_logits = self.model.placement_logits(features, positions, angles)

            # Shift all positions by (+150.0, -85.5) meters
            shifted_positions = positions + torch.tensor([150.0, -85.5])
            shifted_logits = self.model.placement_logits(features, shifted_positions, angles)

        max_diff = torch.max(torch.abs(base_logits - shifted_logits)).item()
        self.assertLess(max_diff, 1e-5, f"Translation invariance violated with max diff: {max_diff}")

    def test_rotation_invariance(self):
        """Logits must be strictly invariant when candidate coordinates and angles are rotated."""
        K = 12
        features = torch.randn(K, server.PLACEMENT_FEATURE_DIM)
        positions = torch.randn(K, 2) * 20.0
        angles = torch.rand(K) * 2.0 * math.pi

        with torch.no_grad():
            base_logits = self.model.placement_logits(features, positions, angles)

            # Test multiple rotation angles: 45 deg, 90 deg, 137 deg, 180 deg
            for rot_deg in (45.0, 90.0, 137.0, 180.0):
                phi = math.radians(rot_deg)
                cos_phi = math.cos(phi)
                sin_phi = math.sin(phi)
                rot_matrix = torch.tensor([[cos_phi, -sin_phi], [sin_phi, cos_phi]], dtype=torch.float32)

                rotated_positions = torch.matmul(positions, rot_matrix.T)
                rotated_angles = (angles + phi) % (2.0 * math.pi)

                rotated_logits = self.model.placement_logits(features, rotated_positions, rotated_angles)
                max_diff = torch.max(torch.abs(base_logits - rotated_logits)).item()
                self.assertLess(
                    max_diff,
                    1e-5,
                    f"Rotation invariance violated at {rot_deg} deg with max diff: {max_diff}",
                )

    def test_single_candidate_and_fallback(self):
        """Model must gracefully handle K=1 candidate or missing coordinates."""
        features_single = torch.randn(1, server.PLACEMENT_FEATURE_DIM)
        with torch.no_grad():
            logits_single = self.model.placement_logits(features_single)
            self.assertEqual(logits_single.shape, (1,))

            features_multi = torch.randn(5, server.PLACEMENT_FEATURE_DIM)
            logits_multi_fallback = self.model.placement_logits(features_multi)
            self.assertEqual(logits_multi_fallback.shape, (5,))

if __name__ == "__main__":
    unittest.main()
