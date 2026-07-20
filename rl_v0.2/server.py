import asyncio
import json
import math
import os
import time
import torch
import torch.nn as nn
import torch.optim as optim
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import uvicorn
import geometry as G

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = FastAPI()

@app.get("/")
async def get_index():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))

@app.get("/app.js")
async def get_app_js():
    return FileResponse(os.path.join(BASE_DIR, "app.js"))

@app.get("/styles.css")
async def get_styles_css():
    return FileResponse(os.path.join(BASE_DIR, "styles.css"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def point_to_loops_dist(pt, loops):
    if not loops: return 999.0
    min_d = 999.0
    for loop in loops:
        n = len(loop)
        for i in range(n):
            a = loop[i]
            b = loop[(i+1)%n]
            dx = b['x'] - a['x']
            dy = b['y'] - a['y']
            l2 = dx*dx + dy*dy
            if l2 < 1e-6:
                d = math.hypot(pt['x'] - a['x'], pt['y'] - a['y'])
            else:
                t = max(0.0, min(1.0, ((pt['x'] - a['x']) * dx + (pt['y'] - a['y']) * dy) / l2))
                proj = {'x': a['x'] + t * dx, 'y': a['y'] + t * dy}
                d = math.hypot(pt['x'] - proj['x'], pt['y'] - proj['y'])
            min_d = min(min_d, d)
    return min_d

# PyTorch Policy Gradient (REINFORCE) Network
class PolicyNetwork(nn.Module):
    def __init__(self, input_dim=12):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 64),
            nn.ReLU(),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, 1)
        )
    def forward(self, x):
        # x: tensor of shape (num_candidates, input_dim)
        return self.net(x).squeeze(-1)

# Modular RL Agent
class PyTorchModularAgent:
    def __init__(self, settings, seed=None, instance_idx=0):
        self.settings = settings
        self.seed = seed or int(time.time())
        self.rng = G.RNG(self.seed)
        self.instance_idx = instance_idx
        
        # Select Device (incorporating Apple Silicon MPS support)
        if torch.cuda.is_available():
            self.device = torch.device("cuda")
        elif torch.backends.mps.is_available():
            self.device = torch.device("mps")
        else:
            self.device = torch.device("cpu")
        print(f"Agent {self.instance_idx} running on device: {self.device}")
        
        self.policy_net = PolicyNetwork(input_dim=12).to(self.device)
        self.optimizer = optim.Adam(self.policy_net.parameters(), lr=settings.get('learningRate', 0.075))
        
        self.baseline = 0.42
        self.episode = 0
        self.score_history = []
        self.best_score = 0
        self.last_score = 0
        self.atrium_values = { 'none': 0.0, 'central': 0.0, 'split': 0.0 }
        self.reset_environment(new_site=True)

    def reset_policy(self):
        self.policy_net = PolicyNetwork(input_dim=12).to(self.device)
        self.optimizer = optim.Adam(self.policy_net.parameters(), lr=self.settings.get('learningRate', 0.075))
        self.baseline = 0.42
        self.score_history = []
        self.best_score = 0
        self.last_score = 0
        self.atrium_values = { 'none': 0.0, 'central': 0.0, 'split': 0.0 }
        self.reset_environment(new_site=True)

    def choose_atrium(self, candidates):
        if self.settings.get('atriumPolicy') == 'none':
            return candidates[0]
        if self.settings.get('atriumPolicy') == 'central':
            return next((c for c in candidates if c['id'] == 'central'), candidates[0])
        epsilon = max(0.08, 0.34 * math.exp(-self.episode / 18.0))
        if self.rng.next_val() < epsilon:
            return self.rng.pick(candidates)
        return max(candidates, key=lambda c: self.atrium_values[c['id']])

    def generate_procedural_pool(self):
        """
        Generates standard rectangular shape templates and a rich set of closed bespoke polygons.
        Allows splayed, sheared, and complex shapes that snap to parameters.
        """
        pool = []
        angle_step = self.settings.get('angleStep', 15)
        min_e = self.settings.get('minEdge', 1.0)
        max_e = self.settings.get('maxEdge', 9.0)
        max_sides = int(self.settings.get('maxEdges', 8))
        
        # 1) Standard rectangular bays
        for w in [3.0, 4.0, 5.0, 6.0, 8.0]:
            for h in [2.0, 3.0, 4.0, 6.0]:
                poly = [{'x':0.0,'y':0.0}, {'x':w,'y':0.0}, {'x':w,'y':h}, {'x':0.0,'y':h}]
                if min_e <= w <= max_e and min_e <= h <= max_e:
                    pool.append({'poly': poly, 'family': 'rectangle'})
                    
        # 2) Procedural bespoke mutations
        angles_choices = [60, 90, 120, 135, 150]
        if angle_step > 0:
            angles_choices = [a for a in angles_choices if a % angle_step == 0]
        lengths_choices = [2.0, 3.0, 4.0, 5.0, 6.0, 8.0]
        lengths_choices = [l for l in lengths_choices if min_e <= l <= max_e]
        
        temp_rng = G.RNG(self.seed + 101)
        for _ in range(350):
            sides = temp_rng.int_range(3, max_sides)
            lengths = [temp_rng.pick(lengths_choices) for _ in range(sides - 1)]
            angles = [temp_rng.pick(angles_choices) for _ in range(sides - 2)]
            poly = G.build_procedural_shape(sides, lengths, angles)
            if poly:
                area = G.polygon_area(poly)
                if area >= 3.0:
                    pool.append({'poly': poly, 'family': f'bespoke-{sides}s'})
        return pool

    def reset_environment(self, new_site=False, shared_dictionary=None):
        if new_site or not hasattr(self, 'boundary'):
            self.site_seed = int(self.rng.next_val() * 0x7fffffff)
            self.boundary = G.make_boundary(self.settings.get('boundaryType', 'lobed'), self.site_seed, self.settings)
            
            # Apply 2x2 grid coordinate offset shifts
            dx = (self.instance_idx % 2) * 65.0
            dy = (self.instance_idx // 2) * 55.0
            self.boundary['outer'] = [{'x': p['x'] + dx, 'y': p['y'] + dy} for p in self.boundary['outer']]
        
        candidates = G.atrium_candidates(self.boundary)
        self.atrium_choice = self.choose_atrium(candidates)
        self.site = G.build_site(self.boundary, self.atrium_choice['holes'])
        
        if shared_dictionary is not None:
            import copy
            self.dictionary = copy.deepcopy(shared_dictionary)
        else:
            # Procedural database pool
            self.shape_pool = self.generate_procedural_pool()
            
            # Dictionary setup (Cores, Corridors, Rooms)
            self.dictionary = []
            dict_cap = int(self.settings.get('dictCap', 10))
            is_public = self.settings.get('publicMode', False)
            
            # Cores (always square service block, 5x5 = 25m2)
            if not self.settings.get('singleFloor'):
                core_poly = [{'x':0,'y':0}, {'x':5,'y':0}, {'x':5,'y':5}, {'x':0,'y':5}]
                self.dictionary.append({
                    'id': 'C1', 'name': 'Service Core', 'category': 'core', 'family': 'square',
                    'poly': core_poly, 'rotations': G.normalize_rotations(core_poly, self.settings.get('angleStep', 15)),
                    'area': G.polygon_area(core_poly), 'uses': 0
                })
                
            # Draw dynamic procedural modules from pool to fill the rest
            room_count = 1
            corridor_count = 1
            for item in self.rng.shuffle(self.shape_pool):
                if len(self.dictionary) >= dict_cap:
                    break
                poly = item['poly']
                area = G.polygon_area(poly)
                
                # Categorize
                if not self.settings.get('singleFloor') and area <= 8.0 and corridor_count <= 2:
                    # Corridor link
                    self.dictionary.append({
                        'id': f'T{corridor_count}', 'name': 'Transit Link', 'category': 'corridor', 'family': item['family'],
                        'poly': poly, 'rotations': G.normalize_rotations(poly, self.settings.get('angleStep', 15)),
                        'area': area, 'uses': 0
                    })
                    corridor_count += 1
                else:
                    # Habitable Room
                    if not is_public and area >= 25.0:
                        continue # Exclude large special rooms if not public mode!
                    cat = 'special' if area >= 25.0 else 'room'
                    name = 'Special Room' if cat == 'special' else 'Room Bay'
                    self.dictionary.append({
                        'id': f'R{room_count}', 'name': name, 'category': cat, 'family': item['family'],
                        'poly': poly, 'rotations': G.normalize_rotations(poly, self.settings.get('angleStep', 15)),
                        'area': area, 'uses': 0
                    })
                    room_count += 1
                
        # Initialize episode orientation basis from angleStep
        angle_step = self.settings.get('angleStep', 15)
        if angle_step > 0:
            steps = [i * angle_step for i in range(int(90 // angle_step) + 1)]
            self.episode_orientation = self.rng.pick(steps)
        else:
            self.episode_orientation = 0
            
        self.placements = []
        self.occupied = {}
        self.log_probs = []
        self.trace = []
        self.done = False
        self.step_count = 0
        self.current_reward = 0.0
        self.metrics = self.compute_metrics()

    def frontier_cells(self):
        if not self.occupied:
            center = G.polygon_centroid(self.site['outer'])
            sorted_cells = sorted(self.site['cells'], key=lambda c: -(self.site['distance'].get(G.key(c['x'],c['y']), 0)))
            return sorted_cells[:60]
        seen = set()
        frontier = []
        for occupied_key in self.occupied.keys():
            x, y = map(int, occupied_key.split(','))
            for dx, dy in [[1,0],[-1,0],[0,1],[0,-1]]:
                nx, ny = x + dx, y + dy
                nk = G.key(nx, ny)
                if nk in seen or nk in self.occupied or nk not in self.site['cellSet']:
                    continue
                seen.add(nk)
                frontier.append({'x': nx, 'y': ny})
        return self.rng.shuffle(frontier)[:36]

    def validate_action_syntax(self, action):
        """
        Implements strict space-syntax:
        - Corridor widths must be narrow (<= 1.5m).
        - Shared edge connection overlap must be at least 0.5m.
        - Gaps and islands are strictly forbidden (entire layout must connect).
        - Travel path distance through standard rooms is restricted.
        """
        module = action['module']
        world_poly = action['worldPoly']
        
        # 1) Corridor Width Constraint
        if module['category'] == 'corridor':
            b = G.bounds_of(world_poly)
            w = min(b['maxX'] - b['minX'], b['maxY'] - b['minY'])
            if w > 1.5:
                return False # corridors must be narrow!

        # 2) Core Spacing Constraint (centroids must be >= 8.0m apart)
        if module['category'] == 'core':
            center = G.polygon_centroid(world_poly)
            for placement in self.placements:
                if placement['module']['category'] == 'core':
                    dist = math.hypot(placement['center']['x'] - center['x'], placement['center']['y'] - center['y'])
                    if dist < 8.0:
                        return False # cores too close!

        # 3) Edge Overlap & Island Connection Check (0.5m shared segment)
        if self.placements:
            connected = False
            for placement in self.placements:
                overlap = G.get_shared_overlap(world_poly, placement['poly'])
                if overlap >= 0.5:
                    connected = True
                    break
            if not connected:
                return False # isolated islands or vertex-touches are illegal!
                
        return True

    def compute_adjacency(self):
        adjacency = {p['id']: set() for p in self.placements}
        for i in range(len(self.placements)):
            for j in range(i + 1, len(self.placements)):
                overlap = G.get_shared_overlap(self.placements[i]['poly'], self.placements[j]['poly'])
                if overlap >= 0.5:
                    adjacency[self.placements[i]['id']].add(self.placements[j]['id'])
                    adjacency[self.placements[j]['id']].add(self.placements[i]['id'])
        return adjacency

    def check_corridor_chains(self, adjacency):
        """
        Verify that no corridors are floating (must reach room/core and terminate at a room).
        """
        corridors = [p for p in self.placements if p['module']['category'] == 'corridor']
        for c in corridors:
            visited = set()
            queue = [c['id']]
            terminated_at_room = False
            while queue:
                curr = queue.pop(0)
                visited.add(curr)
                neighbors = adjacency.get(curr, set())
                for nb_id in neighbors:
                    nb = self.placements[nb_id]
                    if nb['module']['category'] in ['room', 'special', 'core']:
                        terminated_at_room = True
                        break
                    if nb_id not in visited:
                        queue.append(nb_id)
                if terminated_at_room:
                    break
            if not terminated_at_room:
                return False
        return True

    def check_room_transitions(self, adjacency):
        """
        Enforce room transition cap:
        - Standard rooms: max 2 intermediate standard rooms to reach a core.
        - Special rooms: must be connected to a core (crossings can be anything).
        """
        rooms = [p for p in self.placements if p['module']['category'] == 'room']
        special_rooms = [p for p in self.placements if p['module']['category'] == 'special']
        cores = [p for p in self.placements if p['module']['category'] == 'core']
        if not cores:
            return True
            
        for room in rooms:
            # BFS to find path to closest core
            visited = set()
            queue = [(room['id'], 0)] # (current_id, standard_room_crossings)
            reachable = False
            while queue:
                curr_id, crossings = queue.pop(0)
                visited.add(curr_id)
                curr_module = self.placements[curr_id]
                
                if curr_module['module']['category'] == 'core':
                    if crossings <= 3: # room itself + at most 2 intermediate standard rooms
                        reachable = True
                        break
                        
                for nb_id in adjacency.get(curr_id, set()):
                    if nb_id in visited:
                        continue
                    nb = self.placements[nb_id]
                    inc = 1 if nb['module']['category'] == 'room' else 0
                    queue.append((nb_id, crossings + inc))
            if not reachable:
                return False
                
        for s_room in special_rooms:
            # BFS to find any path to a core (no crossings cap)
            visited = set()
            queue = [s_room['id']]
            reachable = False
            while queue:
                curr_id = queue.pop(0)
                visited.add(curr_id)
                curr_module = self.placements[curr_id]
                
                if curr_module['module']['category'] == 'core':
                    reachable = True
                    break
                    
                for nb_id in adjacency.get(curr_id, set()):
                    if nb_id not in visited:
                        queue.append(nb_id)
            if not reachable:
                return False
                
        return True

    def candidate_features(self, module, rotation, anchor_x, anchor_y):
        world_poly = [{'x': p['x'] + anchor_x, 'y': p['y'] + anchor_y} for p in rotation['poly']]
        
        # 1) Exact Vector Containment
        if not G.polygon_inside_site(world_poly, self.site['outer'], self.site['holes']):
            return None
        # 2) Overlap Check
        if any(G.polygons_overlap(world_poly, p['poly']) for p in self.placements):
            return None
            
        # Rasterize for quick cell occupancy check
        cells = G.rasterize_polygon(world_poly)
        if not cells: return None
        for cell in cells:
            ck = G.key(cell['x'], cell['y'])
            if ck not in self.site['cellSet'] or ck in self.occupied:
                return None
                
        # 3) Connectivity check
        action = {'module': module, 'worldPoly': world_poly, 'cells': cells}
        if not self.validate_action_syntax(action):
            return None
            
        # Calculate features
        contact_edges = 0
        external_edges = 0
        daylight_cells = 0
        outer_edge_cells = 0
        candidate_keys = set(G.key(c['x'], c['y']) for c in cells)
        
        # Trace building envelope dynamically (only for daylight checking of rentable spaces)
        if module['category'] in ['room', 'special']:
            temp_keys = list(self.occupied.keys()) + [G.key(c['x'], c['y']) for c in cells]
            envelope_loops = G.trace_boundaries(temp_keys)
            for cell in cells:
                pt_center = {'x': cell['x'] + 0.5, 'y': cell['y'] + 0.5}
                d_wall = point_to_loops_dist(pt_center, envelope_loops)
                if d_wall <= 6.0:
                    daylight_cells += 1
        else:
            daylight_cells = len(cells) # corridors/cores have dummy full daylight to ignore them
            
        for cell in cells:
            k = G.key(cell['x'], cell['y'])
            if (self.site['outerDistance'].get(k) or 999) == 0:
                outer_edge_cells += 1
            for dx, dy in [[1,0], [-1,0], [0,1], [0,-1]]:
                neighbor = G.key(cell['x']+dx, cell['y']+dy)
                if neighbor in self.occupied:
                    contact_edges += 1
                elif neighbor not in candidate_keys:
                    external_edges += 1
                    
        # Feature computation
        coverage = module['area'] / self.max_module_area
        contact = G.clamp(contact_edges / max(2, math.sqrt(len(cells)) * 2), 0, 1)
        reuse = G.clamp(module['uses'] / 4.0, 0.25, 1.0) if module['uses'] > 0 else -0.3
        daylight = (daylight_cells / len(cells))
        
        compactness = G.clamp(contact_edges / max(1, external_edges), 0, 1)
        regularity = module.get('regularity', 0.8)
        
        # Orientation & Alignment
        angle = rotation['angle'] % 180
        basis_delta = abs(angle - self.episode_orientation)
        orientation_feat = 1.0 - min(basis_delta, 180 - basis_delta) / 90.0
        
        # Circulation Bridges & Graph Features
        circulation = 0.5
        if module['category'] == 'corridor':
            outer_exposure = outer_edge_cells / len(cells)
            if outer_exposure > 0.35: return None
            circulation = 1.0 - outer_exposure
            
        travel = 0.5
        cores = [p for p in self.placements if p['module']['category'] == 'core']
        if cores:
            center = G.polygon_centroid(world_poly)
            dist = min(math.hypot(c['center']['x'] - center['x'], c['center']['y'] - center['y']) for c in cores)
            travel = G.clamp(1.0 - dist / 25.0, -1, 1)
            
        return {
            'module': module, 'rotation': rotation, 'worldPoly': world_poly, 'cells': cells,
            'features': [
                coverage, contact, reuse, daylight, compactness, regularity,
                orientation_feat, circulation, 0.5, 0.5, travel, 0.5
            ]
        }

    def generate_candidates(self):
        frontier = self.frontier_cells()
        candidates = []
        seen = set()
        placing_first = len(self.placements) == 0
        has_cores = any(m['category'] == 'core' for m in self.dictionary)
        
        for target in frontier:
            for module in self.dictionary:
                if placing_first and has_cores and module['category'] != 'core':
                    continue # First placement MUST be a core!
                for rot in module['rotations']:
                    anchors = rot['cells'][:4] if len(rot['cells']) > 4 else rot['cells']
                    for anchor in anchors:
                        ax = target['x'] - anchor['x']
                        ay = target['y'] - anchor['y']
                        sig = f"{module['id']}|{rot['angle']}|{ax}|{ay}"
                        if sig in seen: continue
                        seen.add(sig)
                        feat = self.candidate_features(module, rot, ax, ay)
                        if feat:
                            candidates.append(feat)
                            if len(candidates) >= 190:
                                return candidates
        return candidates

    def compute_metrics(self):
        filled_area = sum(p['module']['area'] for p in self.placements) if self.placements else 0
        site_area = self.site['exactArea'] if self.site else 1.0
        fill_ratio = filled_area / max(1.0, site_area)
        
        rentable_area = sum(p['module']['area'] for p in self.placements if p['module']['category'] in ['room', 'special']) if self.placements else 0
        rentable_ratio = rentable_area / max(1.0, filled_area) if filled_area else 0.0
        
        # Calculate dynamic building daylight
        daylight_ratio = 1.0
        if self.placements:
            envelope_loops = G.trace_boundaries(self.occupied.keys())
            daylight_cells = 0
            rentable_cells_count = 0
            for p in self.placements:
                if p['module']['category'] in ['room', 'special']:
                    for cell in p['cells']:
                        rentable_cells_count += 1
                        pt_center = {'x': cell['x'] + 0.5, 'y': cell['y'] + 0.5}
                        if point_to_loops_dist(pt_center, envelope_loops) <= 6.0:
                            daylight_cells += 1
            if rentable_cells_count > 0:
                daylight_ratio = daylight_cells / rentable_cells_count
                
        score = 100.0 * (fill_ratio * 0.45 + rentable_ratio * 0.35 + daylight_ratio * 0.2)
        return {
            'filledArea': filled_area,
            'siteArea': site_area,
            'fillRatio': fill_ratio,
            'rentableArea': rentable_area,
            'rentableRatio': rentable_ratio,
            'daylightRatio': daylight_ratio,
            'score': G.clamp(score, 0, 100),
            'moduleCount': len(self.placements),
            'boundaryViolations': 0,
            'overlapViolations': 0
        }

    def step(self):
        if self.done:
            return { 'done': True, 'metrics': self.metrics }
        
        self.max_module_area = max(1.0, *[m['area'] for m in self.dictionary])
        candidates = self.generate_candidates()
        if not candidates or len(self.placements) >= self.settings.get('maxModules', 130):
            # Check topology at end of episode (strict graph verification)
            adjacency = self.compute_adjacency()
            topo_valid = self.check_corridor_chains(adjacency) and self.check_room_transitions(adjacency)
            
            # Penalize end score heavily if the final layout violates topology
            self.done = True
            self.metrics = self.compute_metrics()
            if not topo_valid:
                self.metrics['score'] = max(0.0, self.metrics['score'] - 45.0)
            
            # Backpropagation
            self.finish_episode()
            return { 'done': True, 'metrics': self.metrics }
            
        # Sample using PyTorch Softmax Policy Network
        features_matrix = [c['features'] for c in candidates]
        features_tensor = torch.tensor(features_matrix, dtype=torch.float32, device=self.device)
        
        logits = self.policy_net(features_tensor)
        temperature = max(0.28, 0.72 * math.exp(-self.episode / 32.0))
        probs = torch.softmax(logits / temperature, dim=0)
        
        m = torch.distributions.Categorical(probs)
        action_idx = m.sample()
        self.log_probs.append(m.log_prob(action_idx))
        
        # Place module
        choice = candidates[action_idx.item()]
        placement_id = len(self.placements)
        for cell in choice['cells']:
            self.occupied[G.key(cell['x'], cell['y'])] = placement_id
            
        choice['module']['uses'] += 1
        self.placements.append({
            'id': placement_id,
            'module': choice['module'],
            'cells': choice['cells'],
            'poly': choice['worldPoly'],
            'center': G.polygon_centroid(choice['worldPoly']),
            'rotation': choice['rotation']['angle'],
            'bornAt': time.time() * 1000
        })
        
        self.step_count += 1
        self.metrics = self.compute_metrics()
        return { 'done': False, 'placement': self.placements[-1], 'metrics': self.metrics }

    def finish_episode(self):
        if not self.log_probs: return
        
        normalized_score = self.metrics['score'] / 100.0
        advantage = G.clamp(normalized_score - self.baseline, -0.5, 0.5)
        
        # Compute policy gradient loss
        policy_loss = []
        for log_prob in self.log_probs:
            policy_loss.append(-log_prob * advantage)
            
        self.optimizer.zero_grad()
        loss = torch.stack(policy_loss).sum()
        loss.backward()
        self.optimizer.step()
        
        self.baseline = 0.88 * self.baseline + 0.12 * normalized_score
        self.score_history.append(self.metrics['score'])
        if len(self.score_history) > 40:
            self.score_history.pop(0)
            
        self.last_score = self.metrics['score']
        self.best_score = max(self.best_score, self.last_score)
        self.episode += 1
        self.log_probs = []

# WebSocket Server API
agents = []
settings = {
    'boundaryType': 'lobed', 'atriumPolicy': 'agent', 'singleFloor': False, 'publicMode': False,
    'minEdge': 1.5, 'maxEdge': 9.0, 'maxEdges': 8, 'dictCap': 10, 'angleStep': 15,
    'learningRate': 0.05, 'maxModules': 130, 'travelLimit': 12
}

def sync_agent_dictionaries(agents, new_site=True):
    # Reset agent 0 to generate/retrieve the master boundary and dictionary
    agents[0].reset_environment(new_site=new_site)
    shared_dict = agents[0].dictionary
    
    # Synchronize all other agents to use the exact same dictionary
    for i in range(1, len(agents)):
        agents[i].reset_environment(new_site=new_site, shared_dictionary=shared_dict)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global agents, settings
    await websocket.accept()
    print("Client connected via WebSocket")
    
    # Initialize 4 parallel agent instances
    agents = [PyTorchModularAgent(settings, seed=settings.get('seed', 123) + i, instance_idx=i) for i in range(4)]
    sync_agent_dictionaries(agents, new_site=True)
    
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            cmd = msg.get('cmd')
            
            if cmd == 'updateSettings':
                settings.update(msg.get('settings', {}))
                for a in agents:
                    a.settings = settings
                sync_agent_dictionaries(agents, new_site=True)
                await websocket.send_text(json.dumps({'type': 'ack', 'msg': 'settings updated'}))
                
            elif cmd == 'resetPolicy':
                for a in agents:
                    a.reset_policy()
                await websocket.send_text(json.dumps({'type': 'ack', 'msg': 'policy reset'}))
                
            elif cmd == 'saveCheckpoint':
                checkpoint_dir = os.path.join(BASE_DIR, "outputs")
                os.makedirs(checkpoint_dir, exist_ok=True)
                torch.save(agents[0].policy_net.state_dict(), os.path.join(checkpoint_dir, "checkpoint.pt"))
                for i in range(1, 4):
                    agents[i].policy_net.load_state_dict(agents[0].policy_net.state_dict())
                await websocket.send_text(json.dumps({'type': 'ack', 'msg': 'checkpoint saved'}))
                
            elif cmd == 'newSite':
                sync_agent_dictionaries(agents, new_site=True)
                
                # Combine boundaries and holes for 2x2 layout rendering
                boundaries = []
                for a in agents:
                    boundaries.append({
                        'outer': a.boundary['outer'],
                        'holes': a.atrium_choice['holes'] if (a.atrium_choice and a.atrium_choice['holes']) else []
                    })
                
                # Send back the boundary layout
                await websocket.send_text(json.dumps({
                    'type': 'site',
                    'boundaries': boundaries,
                    'device': agents[0].device.type,
                    'dictionary': [{'id': m['id'], 'category': m['category'], 'poly': m['poly'], 'uses': m['uses']} for m in agents[0].dictionary]
                }))
                
            elif cmd == 'step':
                placements_this_step = []
                all_done = True
                
                # Step each agent
                for idx, a in enumerate(agents):
                    res = a.step()
                    if not res['done']:
                        all_done = False
                        p = res['placement']
                        placements_this_step.append({
                            'id': p['id'],
                            'poly': p['poly'],
                            'center': p['center'],
                            'rotation': p['rotation'],
                            'module': {'id': p['module']['id'], 'category': p['module']['category']},
                            'instanceIdx': idx
                        })
                
                if all_done:
                    # Select metrics from best agent
                    best_agent = max(agents, key=lambda a: a.metrics.get('score', 0))
                    
                    await websocket.send_text(json.dumps({
                        'type': 'episodeDone',
                        'metrics': best_agent.metrics,
                        'scoreHistory': best_agent.score_history,
                        'bestScore': best_agent.best_score,
                    }))
                    
                    # Reset all for next episode
                    for a in agents:
                        a.reset_environment(new_site=False)
                else:
                    # Send placements for this parallel step
                    await websocket.send_text(json.dumps({
                        'type': 'placements',
                        'placements': placements_this_step
                    }))
                        
    except Exception as e:
        print(f"WebSocket Connection closed: {e}")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
