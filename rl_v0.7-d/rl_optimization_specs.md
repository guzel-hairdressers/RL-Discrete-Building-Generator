# Instruction Set: Modular Floor Plan Optimization Algorithm (RL)

## 1. Project Context & Objectives
- **Reference Prototype**: There is a simplified, non-RL space-filling prototype located in the [simplified_no_rl_prototype](file:///Users/ruslan_faz/Desktop/Work/Thesis/simplified_no_rl_prototype/) directory. You can examine these files for inspiration, but you absolutely do not have to use or build on top of those files' logic; you can get inspired by it, and you can completely rewrite the prototype logic if you feel like it's the better way.
- **Optimization Task**: The next step is to create the optimization algorithm (RL). 
- **Modular Filling**: Right now, the space generates a boundary and boundary holes that must not be crossed by the plan geometry. You do not have to create the actual floor plan but rather fill the provided space with modular shapes that can be thought of as modular structures that are gonna be pre-fabricated and assembled on the site but dont think too much about the real-world sense of that, just that the space has to be filled with modular shapes from the shapes dictionary.
- **Site Boundaries & Atriums**:
  - The outside boundary is like the site boundary.
  - The boundary holes are like atriums (so that you see the future physical sense of that), because there can also be model-generated holes.
  - Boundary and boundary holes should be of reasonable real-world-related sizes in meters but geometries can vary, sizes can also vary based on the building type.
  - When the algorithm is gonna be used, the outside boundary will be fixed (site boundary is fixed in real world), but the boundary holes are gonna be decided by the algorithm if it decides that they are needed (also their sizes, placements, amounts, shapes and other parameters if you can come up with any).

## 2. Shapes Dictionary & Modules
- **Dynamic Modules**: The shapes dictionary is not predetermined. You are creating the modules instead.
- **Parametrization**: The modules should be parametrizable so that their shapes can be optimized.
- **Placement & Rotation**: Once a modular shape is placed on the canvas it is added to the shapes dictionary and its internal parameters (edge lengths, angles between edges) cannot be changed and that module should be used without changes, it can only be placed and rotated to fill in the space (no type of scaling is allowed).
- **Reusability**: Modules can and should be utilized multiple times (if some are placed only once, it's ok but not optimal as the point of the whole modular workflow is reusability).
- **Internal Holes/Voids**: Holes inbetween the placed shapes that dont relate to the boundary holes are probably not ideal as they basically become an unused space inside the building that isnt filled with anything and if they are too small they also dont introduce any light inside the building (you can evaluate and propose some constraints yourself using physical sense). This is not a constraint but instead a suggestion: if the algorithm sees that some unfilled spaces are benefitial to the geometry - add them.

## 3. Module Geometry & Connections
- **Module Shapes**: Amount of edges, edge lengths, angles between edges in each module should be parametrizable so that the model can control them to optimize the overall plan.
- **Triangles**: Placement of triangles should be discouraged as they naturally create sharp angles (which are fine in some cases), they should be used as the last resort or in order to fill in the holes (if the holes need to be filled). Note that remaining empty holes do not have to be filled (if the algorithm decides that they are beneficial).
- **Symmetry & Angles**:
  - Regularity of polygons is not that important but if you find it beneficial - use that.
  - Having straight angles is very good (a good building practice), but not very important.
- **Connections**: One of the reasonable ways for modules' connection is to connect with one, two or more sides. Modules do not have to completely connect by their sides (but strongly encouraged); if they connect by some portion of an edge, that is acceptable. Some modules may fill in the created holes, but the amount of modules is constrained (also remember that modules are preferred to be used more than once).
- **No Collisions**: Modules should not have collisions, they shouldnt intersect or consume outside boundaries and boundary holes.
- **Control**: Modules placements and rotations are controlled by the model.

## 4. Constraints (Controllable Settings)
The following constraints should be controllable:
- **Edge Lengths**: Constrained at least $1$m, at most $9$m.
- **Angles Between Edges**: Should be more than $40$ degrees (or else that creates weird unusable spaces, again think in a physical-world application sense).
- **Angle Increments**: Should be multiples of some amount of degrees (in prototype $15^\circ$ multiples were used, can be $10^\circ$ or $7.5^\circ$).
- **Max Edges**: Maximum number of edges per module (as a default set it to $8$).
- **Module Size Ratio**: The smallest module should be at most $5$ times smaller than the biggest module.
- **Module Caps**: There's a cap on the amount of placed modules and there's a cap on the shapes dictionary length.

## 5. Metrics to Collect
The metrics proposed now are not final and you should also propose some others. We probably need:
- **Filled Area
- **Fill Ratio**: Proportion of filled area to the overall site area (with or without the boundary holes, not sure yet).
- **Perimeters**: Outside perimeter and inside perimeter.
- **Envelope Efficiency**: Proportion of outside perimeter to the area (lower - better probably).
- **Module Count**: Amount of modules used.
- **Dictionary Length**: Length of modules dictionary.
- **Module Size Ratio**: Proportion of smallest to biggest modules' area.
- **Light & Enclosure Evaluation**: The boundaries of the created shapes should also somehow be checked for specific metrics, some boundaries might create narrow or practically enclosed shapes that wont allow almost no light to pass inside (maybe simplified light simulations or simplified methods for evaluating boundaries).
- **Constructibility Score**: Some boundaries are technologically bad, as they would be hard to build (maybe you find how to turn that into a measurable number). This is not very crucial now, but maybe it is better to collect.
- **Global Shape Irregularity**: Weirdness or irregularity of the global shape is not that important but if you can assess that - you can also collect it.

## 6. Exposed UI Controls
In addition to the controls mentioned in constraints section, the UI should expose:
- **Animation Speed**: Space filling animation speed control.
- **Window Navigation**: Scale and panning. By default, the whole thing should fit inside the program/website window. Panning and zooming can have controls but should preferably be controlled by mouse or touchpad (there might be a control to reset zoom though).
- **Scale Bar**: Showing the correct scale, copied from the prototype's geographic staggered scale bar design.

## 7. Future Scalability & Multi-Floor Stackability
- **Curriculum Note**: We are NOT developing a multi-floor algorithm right now (we are only designing 1 floor), and we do NOT perform structural core matching, corridor matching, or edge matching right now. However, the algorithm should be designed for future scalability in a multi-floor way.
- **Scaling/Supervision Plan**: In the future this algorithm is gonna be either scaled up or supervised by another algorithm, which is gonna stack multiple floor plans on top of each-other to create multi-level buildings, so the algorithm should also think about scalability or providing a bunch of adjustable parameters for control.
- **Stacking Logic (Future)**: For future uses the plans are gonna be put on top of each other so some elements on the floor plans should match (to make structural sense). The way I think about it right now is that there should be modules of the core of the building that should either be unchangeable from floor to floor or they should have at least 75% match in edges. There are also gonna be corridors or other transitional spaces that should have some degree of plan-to-plan matching (maybe at least 30%). Other spaces may or may not have matches but generally matches in edges should be somewhat encouraged.
- **Module Classification**: You do not need to design multiple floors now, this is mentioned for planned future scalability. For now, you need to mark certain modules as Cores, certain modules as corridors/transitional spaces (there may be 0 of them), other modules as rooms/main spaces.
- **Optimal Placements & Distances**: 
  - Maybe it doesn't make sense to put cores close to each other but the model should be able to learn their optimal placement.
  - Maybe it should start with putting in cores, and then drawing corridors and then other spaces, maybe not.
  - Travel distances from rooms/main spaces to cores should be constrained (maybe add a control).
- **Single-Floor Checkbox**: Add a checkbox or something that asks whether a building is only 1 floor, so that some of those stackability/core things in this section can be disregarded (a 1-floor building probably wouldn't need cores and won't have to be designed for stackability, but travel distances should still be constrained). Right now, this checkbox should only control whether we need to mark cores/corridors or don't.
