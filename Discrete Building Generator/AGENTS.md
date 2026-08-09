# Instructions for v0.8 (Human remarks)

This version you see is an attempt to optimize v0.6-d (you can visit https://github.com/guzel-hairdressers/RL-Discrete-Building-Generator for other branches and versions). you can check stuff in README.md files about the versions. This version was chosen because it achieves a bit more variation than v0.6-b (v0.7-b is an attempt to optimize v-0.6b and is significantly faster tbh but im not sure that the generation quality is the same but generations look pretty much the same). v0.7b is way better optimized than v0.7-d. 
We're gonna continue with this v0.7-d and with v0.6-c because they are most relevant to what i want to achieve in the long run.
Your primary task for this v0.8 versions is OPTMIMIZATION. it can be putting the whole thing on gpu, parallelization, writing custom kernels, rewrite on C or Rust or smth else, maths optimization, algorithm remake, any other changes that dont sacrifice current capabilities but achieve speed up and possibly increased functionality and variation in generated shapes and smth else. The current algorithm for generation is REINFORCE with a bunch of extra geometry check and proposal steps. Time these steps, measure memory use, optimize. speed is the goal. Dont 
You dont have to use this algorithm as a baseline, maybe a full rewrite is better, but you can get inspired by this and see what steps i tried before. UI is also a subject to change. but it would be nice to have some debugging functions in the ui (maybe initially hidden before some shortcut is used). 
Optimized v0.6-c should become v0.8.0, optimized v0.7-d should become v0.8.1 (no need to push anything to gh, just two folders as output, one for v0.8.0, another for v0.8.1)
I run the thing on mac primarily because i develop and iterate code on it but i have an access to acomputer with 2x rtx 5080s for big runs. optimizations should work for both systems. 
REINFORCE has a high variance in my runs, each step runs 4 instances (they might be called playgrounds in code) of the algorithm, to decrease variance i can run more but it costs time as the thing is not very optimized rn. maybe instead of REINFORCE other algorithms like TD(n) or PPO+GAE or off-policy methods make more sense to have more stable gradients. specifically td will also have more intermediate updates so maybe it will converge faster and better. intermediate step updates could use a proxy value function because the actual one with all the checks is too expensive rn but maybe its solvable.
Checks. on each step before shape placement or new shape generation there are a bunch of evaluations of shape boundaries and collisions. if some of those expensive and exhaustive checks could be avoided or simplified (possible restriction of the options with some heuristics mb) while not harming the generaion quality and diversity - that would be nice.
Graphs. Instead of treating this as a 2d polygon problem in a 2d grid maybe its better to try graphs approach for shape placement and generation steps (theres a 'mb_bs_graphs_proposal.md', take it with a grain of salt). nodes with connected edges and exposed edges and ports can describe shape relationships without explicitly specifying edge lengths and internal shape angles. and such networks of graphs could be used for limiting proposed placement or shape options, and they might be used in some attention graph mechanishm for policy learning (might be bs). if that thing works out - graph versions of v0.8.0 and v0.8.1
Core. v0.8.0 shouldnt build on top of v0.6-c but the idea is the same - each instance or playground on which the algorithm runs should be treated as a building floor and placing a core means its gonna be placed on other floors as well so this version is an attempt to ground this thing in reality a bit. v0.6-c that was attempted before really suffers from even worse speed performance than other versions and terrible variation and that last time you just used huge rectangular boundaries that almost dont restrict the model which defeats the purpose of creating the algorithm that adapts to diverse and maybe even strange boundary conditions and it almost couldnt learn. you probably should use boundaries larger than the ones generated for other versions, if there is still no valid placement for a core another boundary should probably be requested. lets focus on 4-8 stories (so 4-8 parallel instances/playgrounds, that number can change between episodes).
model score/reward graph is needed. if you think that reward function is broken or doesnt allow for a model to learn in the best way - you can change it or make penalties variable or smth else but try to understand the reasoning behind the established penalties and rewards structure
Preferable speed-up 5-10x for an average episodes if possible, if even more is possible - please do the most you can. evaluate the average time on the first 10-20 episodes


# Agent Instructions & Project Architecture

Welcome to the **RL-Discrete-Building-Generator** (Module Lab) codebase. This repository contains a parallel floor-plan Reinforcement Learning (RL) generator accelerated with low-level C vector geometry and lazy rasterization.

---

## 1. Versioning & Governance Structure

- **`main` Branch**: Contains the authoritative **`v0.7-D`** release at the repository root. All legacy nested subdirectories (`rl_v0.1` through `rl_v0.7-d`) have been cleaned up and consolidated.
- **Variant Branches**: Experimental side branches are preserved in dedicated Git branches:
  - `version/v0.6-a`: Alternative candidate placement anchor search.
  - `version/v0.6-b`: Dynamic palette & parametric proposals variant.
  - `version/v0.6-c`: Frontier growth scoring and core stacking experiment.
  - `version/v0.6-e`: Relative frontier reward shaping and BPE penalty weighting.
  - `version/v0.7-b`: PyTorch MPS device baseline.
  - `prototype/simplified_no_rl`: Heuristic p5.js prototype generator.

---

## 2. Key Architecture Components

- **`server.py`**: FastAPI & WebSocket backend. Manages parallel floor plan environments (`FloorEnvironment`), PyTorch policy training (`ParallelTrainer`), and WebSocket telemetry streaming.
- **`geometry.py`**: Vector geometry kernel. Contains Python SAT overlap checks, `_LazyRotationDict` on-demand cell rasterization, and `ctypes` bindings to `fast_geometry.c`.
- **`fast_geometry.c`**: Low-level C extension implementing native SAT polygon overlap (`polygons_overlap_c`) and point-in-polygon containment (`polygon_inside_site_c`).
- **`graph.py`**: BPE polygon merging, adjacency detection, and layout extraction with AABB pre-filtered placement port matching.
- **`index.html`, `app.js`, `styles.css`**: Live HTML5 Canvas frontend. Renders parallel floor sites, HUD metrics, and placement steps in real time.

---

## 3. Running & Verifying Code

### Run Web Daemon
```bash
python3 server.py
```
Open `http://localhost:8000` in your web browser to view live training.

### Run Unit Tests
```bash
python3 -m unittest discover -s tests -p "test_*.py"
```

### Run Performance Benchmarks
```bash
python3 scratch/benchmark.py
```
Check that average step duration remains low (<50ms per step) and episode duration stays performant (<250ms per episode).
