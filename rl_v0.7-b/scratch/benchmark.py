import sys
import os
import time
import cProfile
import pstats

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import ParallelTrainer

def run_benchmark(num_episodes=10):
    print(f"--- Running Benchmark for {num_episodes} episodes ---", flush=True)
    trainer = ParallelTrainer()
    trainer.new_site()
    
    profiler = cProfile.Profile()
    profiler.enable()
    
    start_time = time.perf_counter()
    completed_episodes = 0
    total_steps = 0
    
    while completed_episodes < num_episodes:
        gen_id = trainer.generation_id
        ep_id = trainer.episode
        result = trainer.step(gen_id, ep_id)
        total_steps += 1
        
        if result.get("type") == "episodeDone":
            completed_episodes += 1
            print(f"Completed Episode {completed_episodes}/{num_episodes} (Total steps so far: {total_steps})", flush=True)
            
    total_time = time.perf_counter() - start_time
    profiler.disable()
    
    print(f"\nCompleted {num_episodes} episodes in {total_time:.2f}s ({total_time / num_episodes:.2f}s / episode)", flush=True)
    print(f"Total steps: {total_steps} ({total_time / total_steps * 1000:.1f}ms / step)", flush=True)
    
    print("\n--- Performance Timings Summary ---", flush=True)
    summary = trainer.step_profiler.summary()
    for key, data in summary.items():
        print(f"  {key:<22}: Avg={data['avg']:6.2f}ms | Min={data['min']:6.2f}ms | Max={data['max']:6.2f}ms | N={data['count']}", flush=True)
        
    print("\n--- cProfile Top 25 Functions by Cumulative Time ---", flush=True)
    ps = pstats.Stats(profiler).sort_stats('cumulative')
    ps.print_stats(25)

if __name__ == "__main__":
    run_benchmark(10)
