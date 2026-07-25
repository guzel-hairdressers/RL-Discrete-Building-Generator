import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import ParallelTrainer, DEFAULT_SETTINGS

def test_all():
    print("Testing site generation with all boundary types...")
    trainer = ParallelTrainer()
    
    boundary_types = ["lobed", "lshape", "ushape", "tshape", "convex", "rect", "free"]
    
    for btype in boundary_types:
        print(f"Testing boundary type: {btype}")
        try:
            settings = dict(DEFAULT_SETTINGS)
            settings["boundaryType"] = btype
            trainer.update_settings(settings)
            print(f"  Successfully updated settings and generated {btype}")
        except Exception as e:
            print(f"  FAILED boundary {btype}: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    test_all()
