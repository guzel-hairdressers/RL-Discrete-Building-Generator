import re

with open("/Users/ruslan_faz/Desktop/Work/Thesis/rl_v0.6-b/server.py", "r") as f:
    content = f.read()

# 1. Add StepProfiler
profiler_code = """class StepProfiler:
    \"\"\"Lightweight per-episode timing profiler for step and evaluation phases.\"\"\"
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        self._samples: dict[str, list[float]] = {}
    
    def record(self, label: str, duration_seconds: float) -> None:
        self._samples.setdefault(label, []).append(duration_seconds * 1000.0)  # Store as ms
    
    def summary(self) -> dict[str, Any]:
        result = {}
        for label, values in self._samples.items():
            if values:
                result[label] = {
                    "avg": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values),
                    "count": len(values),
                }
        return result


class ParallelTrainer:"""
content = content.replace("class ParallelTrainer:", profiler_code)

# 2. Add to __init__
content = content.replace(
    "        self.device = select_device()",
    "        self.device = select_device()\n        self.step_profiler = StepProfiler()"
)

# 3. Add to generation reset
content = content.replace(
    "        self.topology_multiplier = 0.05",
    "        self.topology_multiplier = 0.05\n        self.step_profiler.reset()"
)

with open("/Users/ruslan_faz/Desktop/Work/Thesis/rl_v0.6-b/server.py", "w") as f:
    f.write(content)
