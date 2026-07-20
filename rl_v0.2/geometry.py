# ============================================================
# MODULAR SPACE FILLING GEOMETRY KERNEL (Python)
# ============================================================

import math
import random

EPSILON = 1e-7

def key(x, y):
    return f"{int(x)},{int(y)}"

def clamp(val, min_val, max_val):
    return max(min_val, min(max_val, val))

class RNG:
    def __init__(self, seed):
        self.state = int(seed) & 0xffffffff
    def next_val(self):
        self.state = (self.state + 0x6D2B79F5) & 0xffffffff
        t = self.state
        t = math_imul(t ^ (t >> 15), t | 1)
        t ^= (t + math_imul(t ^ (t >> 7), t | 61)) & 0xffffffff
        return ((t ^ (t >> 14)) & 0xffffffff) / 4294967296.0
    def int_range(self, min_val, max_val):
        return int(self.next_val() * (max_val - min_val + 1)) + min_val
    def pick(self, items):
        if not items: return None
        return items[int(self.next_val() * len(items))]
    def shuffle(self, items):
        shuffled = list(items)
        for i in range(len(shuffled) - 1, 0, -1):
            j = self.int_range(0, i)
            shuffled[i], shuffled[j] = shuffled[j], shuffled[i]
        return shuffled

def math_imul(a, b):
    a = a & 0xffffffff
    b = b & 0xffffffff
    val = (a * b) & 0xffffffff
    if val & 0x80000000:
        val = val - 0x100000000
    return val

def polygon_area(poly):
    sum_val = 0.0
    n = len(poly)
    for i in range(n):
        a = poly[i]
        b = poly[(i + 1) % n]
        sum_val += a['x'] * b['y'] - b['x'] * a['y']
    return abs(sum_val) / 2.0

def polygon_signed_area(poly):
    sum_val = 0.0
    n = len(poly)
    for i in range(n):
        a = poly[i]
        b = poly[(i + 1) % n]
        sum_val += a['x'] * b['y'] - b['x'] * a['y']
    return sum_val / 2.0

def reflex_vertex_count(poly):
    area = polygon_signed_area(poly)
    sign = 1.0 if area >= 0 else -1.0
    count = 0
    n = len(poly)
    for i in range(n):
        prev = poly[(i - 1 + n) % n]
        pt = poly[i]
        nxt = poly[(i + 1) % n]
        if sign * orientation(prev, pt, nxt) < -EPSILON:
            count += 1
    return count

def polygon_perimeter(poly):
    sum_val = 0.0
    n = len(poly)
    for i in range(n):
        a = poly[i]
        b = poly[(i + 1) % n]
        sum_val += math.hypot(b['x'] - a['x'], b['y'] - a['y'])
    return sum_val

def polygon_centroid(poly):
    cx = sum(p['x'] for p in poly)
    cy = sum(p['y'] for p in poly)
    return {'x': cx / len(poly), 'y': cy / len(poly)}

def point_in_polygon(pt, poly):
    x, y = pt['x'], pt['y']
    inside = False
    n = len(poly)
    for i in range(n):
        j = (i - 1 + n) % n
        xi, yi = poly[i]['x'], poly[i]['y']
        xj, yj = poly[j]['x'], poly[j]['y']
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) if (yj - yi) != 0 else 1e-9) + xi):
            inside = not inside
    return inside

def point_on_segment(pt, a, b, epsilon=EPSILON):
    cross = (pt['x'] - a['x']) * (b['y'] - a['y']) - (pt['y'] - a['y']) * (b['x'] - a['x'])
    if abs(cross) > epsilon:
        return False
    dot = (pt['x'] - a['x']) * (b['x'] - a['x']) + (pt['y'] - a['y']) * (b['y'] - a['y'])
    if dot < -epsilon:
        return False
    len_sq = (b['x'] - a['x'])**2 + (b['y'] - a['y'])**2
    return dot <= len_sq + epsilon

def point_on_polygon(pt, poly):
    n = len(poly)
    for i in range(n):
        if point_on_segment(pt, poly[i], poly[(i + 1) % n]):
            return True
    return False

def point_strictly_inside(pt, poly):
    return not point_on_polygon(pt, poly) and point_in_polygon(pt, poly)

def orientation(a, b, c):
    return (b['x'] - a['x']) * (c['y'] - a['y']) - (b['y'] - a['y']) * (c['x'] - a['x'])

def proper_segments_intersect(a, b, c, d):
    o1 = orientation(a, b, c)
    o2 = orientation(a, b, d)
    o3 = orientation(c, d, a)
    o4 = orientation(c, d, b)
    return (((o1 > EPSILON and o2 < -EPSILON) or (o1 < -EPSILON and o2 > EPSILON)) and
            ((o3 > EPSILON and o4 < -EPSILON) or (o3 < -EPSILON and o4 > EPSILON)))

def polygon_edges_intersect(a, b):
    na = len(a)
    nb = len(b)
    for i in range(na):
        for j in range(nb):
            if proper_segments_intersect(a[i], a[(i + 1) % na], b[j], b[(j + 1) % nb]):
                return True
    return False

def segment_breakpoints(a, b, poly):
    dx, dy = b['x'] - a['x'], b['y'] - a['y']
    den_len = dx*dx + dy*dy
    breaks = [0.0, 1.0]
    n = len(poly)
    for i in range(n):
        c = poly[i]
        d = poly[(i + 1) % n]
        ex, ey = d['x'] - c['x'], d['y'] - c['y']
        den = dx * ey - dy * ex
        if abs(den) > EPSILON:
            qx, qy = c['x'] - a['x'], c['y'] - a['y']
            t = (qx * ey - qy * ex) / den
            u = (qx * dy - qy * dx) / den
            if t >= -EPSILON and t <= 1 + EPSILON and u >= -EPSILON and u <= 1 + EPSILON:
                breaks.append(clamp(t, 0.0, 1.0))
        elif abs(orientation(a, b, c)) <= EPSILON and den_len > EPSILON:
            for pt in [c, d]:
                t = ((pt['x'] - a['x']) * dx + (pt['y'] - a['y']) * dy) / den_len
                if t >= -EPSILON and t <= 1 + EPSILON:
                    breaks.append(clamp(t, 0.0, 1.0))
    breaks.sort()
    unique_breaks = []
    for val in breaks:
        if not unique_breaks or abs(val - unique_breaks[-1]) > EPSILON:
            unique_breaks.append(val)
    return unique_breaks

def segment_intervals_pass(a, b, poly, predicate):
    breaks = segment_breakpoints(a, b, poly)
    for i in range(len(breaks) - 1):
        if breaks[i + 1] - breaks[i] <= EPSILON:
            continue
        t = (breaks[i] + breaks[i + 1]) / 2.0
        pt = {'x': a['x'] + (b['x'] - a['x']) * t, 'y': a['y'] + (b['y'] - a['y']) * t}
        if not predicate(pt, poly):
            return False
    return True

def polygons_overlap(a, b):
    # Pre-filter using bounding boxes to speed up checks dramatically
    ba = bounds_of(a)
    bb = bounds_of(b)
    if (ba['maxX'] < bb['minX'] - 1e-4 or ba['minX'] > bb['maxX'] + 1e-4 or
        ba['maxY'] < bb['minY'] - 1e-4 or ba['minY'] > bb['maxY'] + 1e-4):
        return False

    if polygon_edges_intersect(a, b):
        return True
    na = len(a)
    for i in range(na):
        if not segment_intervals_pass(a[i], a[(i + 1) % na], b, lambda p, poly: not point_strictly_inside(p, poly)):
            return True
    nb = len(b)
    for i in range(nb):
        if not segment_intervals_pass(b[i], b[(i + 1) % nb], a, lambda p, poly: not point_strictly_inside(p, poly)):
            return True
    for pt in a:
        if point_strictly_inside(pt, b):
            return True
    for pt in b:
        if point_strictly_inside(pt, a):
            return True
    return False

def polygon_inside_site(poly, outer, holes=[]):
    for pt in poly:
        if not point_in_polygon(pt, outer) and not point_on_polygon(pt, outer):
            return False
    n = len(poly)
    for i in range(n):
        a = poly[i]
        b = poly[(i + 1) % n]
        if not segment_intervals_pass(a, b, outer, lambda p, boundary: point_in_polygon(p, boundary) or point_on_polygon(p, boundary)):
            return False
    for hole in holes:
        if polygons_overlap(poly, hole):
            return False
    return True

def bounds_of(poly):
    xs = [p['x'] for p in poly]
    ys = [p['y'] for p in poly]
    return {'minX': min(xs), 'maxX': max(xs), 'minY': min(ys), 'maxY': max(ys)}

def rotate_polygon(poly, angle_degrees):
    angle = math.radians(angle_degrees)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    rotated = [{'x': p['x'] * cos_a - p['y'] * sin_a, 'y': p['x'] * sin_a + p['y'] * cos_a} for p in poly]
    b = bounds_of(rotated)
    return [{'x': p['x'] - b['minX'], 'y': p['y'] - b['minY']} for p in rotated]

def rasterize_polygon(poly):
    b = bounds_of(poly)
    cells = []
    for y in range(math.floor(b['minY']), math.ceil(b['maxY'])):
        for x in range(math.floor(b['minX']), math.ceil(b['maxX'])):
            center = {'x': x + 0.5, 'y': y + 0.5}
            if point_in_polygon(center, poly):
                cells.append({'x': x, 'y': y})
    return cells

def normalize_rotations(poly, angle_step):
    rotations = []
    signatures = set()
    steps = max(1, round(360 / angle_step))
    for r in range(steps):
        angle = r * angle_step
        rotated_poly = rotate_polygon(poly, angle)
        cells = rasterize_polygon(rotated_poly)
        signature = '|'.join(f"{p['x']:.3f},{p['y']:.3f}" for p in rotated_poly)
        if signature in signatures:
            continue
        signatures.add(signature)
        b = bounds_of(rotated_poly)
        rotations.append({
            'rotation': r,
            'angle': angle,
            'poly': rotated_poly,
            'cells': cells,
            'width': b['maxX'] - b['minX'],
            'height': b['maxY'] - b['minY']
        })
    return rotations

def convex_hull(points):
    sorted_pts = sorted(points, key=lambda p: (p['x'], p['y']))
    if len(sorted_pts) <= 3:
        return sorted_pts
    lower = []
    for p in sorted_pts:
        while len(lower) >= 2 and orientation(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(sorted_pts):
        while len(upper) >= 2 and orientation(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]

def translate_to_origin(poly):
    b = bounds_of(poly)
    return [{'x': p['x'] - b['minX'], 'y': p['y'] - b['minY']} for p in poly]

def make_boundary(bnd_type, seed, options):
    rng = RNG(seed)
    outer = []
    family = bnd_type
    
    if bnd_type == 'lshape':
        w = rng.int_range(29, 35)
        h = rng.int_range(23, 28)
        cutW = rng.int_range(10, 14)
        cutH = rng.int_range(9, 13)
        outer = [{'x': x, 'y': y} for x, y in [
            (0,0), (w,0), (w, h-cutH), (w-cutW, h-cutH), (w-cutW, h), (0, h)
        ]]
    elif bnd_type == 'ushape':
        w = rng.int_range(32, 38)
        h = rng.int_range(23, 28)
        arm = rng.int_range(7, 9)
        courtDepth = rng.int_range(10, 14)
        outer = [{'x': x, 'y': y} for x, y in [
            (0,0), (w,0), (w,h), (w-arm,h), (w-arm,h-courtDepth), (arm,h-courtDepth), (arm,h), (0,h)
        ]]
    elif bnd_type == 'tshape':
        w = rng.int_range(31, 39)
        bar = rng.int_range(7, 10)
        stemW = rng.int_range(11, 16)
        stemH = rng.int_range(15, 21)
        stemX = rng.int_range(5, w - stemW - 5)
        outer = [{'x': x, 'y': y} for x, y in [
            (0,0), (w,0), (w,bar), (stemX+stemW,bar), (stemX+stemW,bar+stemH), (stemX,bar+stemH), (stemX,bar), (0,bar)
        ]]
        family = 'randomized T'
    elif bnd_type == 'convex':
        w, h = rng.int_range(32, 40), rng.int_range(23, 30)
        pts = [{'x': rng.int_range(0, w), 'y': rng.int_range(0, h)} for _ in range(22)]
        pts.extend([
            {'x': 0, 'y': rng.int_range(5, h-5)},
            {'x': w, 'y': rng.int_range(5, h-5)},
            {'x': rng.int_range(5, w-5), 'y': 0},
            {'x': rng.int_range(5, w-5), 'y': h}
        ])
        outer = translate_to_origin(convex_hull(pts))
        family = 'convex hull'
    elif bnd_type == 'lobed':
        count = clamp(int(options.get('boundaryVertices', rng.int_range(13, 19))), 10, 24)
        lobe_count = clamp(int(options.get('lobeCount', rng.int_range(3, 6))), 2, count // 2)
        reach = clamp(float(options.get('lobeReach', 1.55)), 1.1, 2.2)
        notch_depth = clamp(float(options.get('concavity', 0.62)), 0.25, 0.82)
        global_rotation = rng.next_val() * 2 * math.pi
        aspect_angle = rng.next_val() * 2 * math.pi
        rx, ry = rng.int_range(14, 18), rng.int_range(11, 16)
        cx, cy = 20, 18
        indices = list(range(count))
        rng.shuffle(indices)
        lobes = []
        for candidate in indices:
            if all(min(abs(idx - candidate), count - abs(idx - candidate)) >= 2 for idx in lobes):
                lobes.append(candidate)
            if len(lobes) >= lobe_count:
                break
        lobe_set = set(lobes)
        notches = set()
        for lobe_idx, idx in enumerate(lobes):
            direction = 1 if lobe_idx % 2 == 0 else -1
            notches.add((idx + direction + count) % count)
            if lobe_idx < math.ceil(lobe_count / 2):
                notches.add((idx - direction + count) % count)
        outer = []
        for i in range(count):
            angle = global_rotation + (i / count) * 2 * math.pi + (rng.next_val() - 0.5) * 0.07
            radius = 0.76 + rng.next_val() * 0.25
            if i in lobe_set:
                radius = reach * (0.78 + rng.next_val() * 0.34)
            if i in notches:
                radius = 1.0 - notch_depth * (0.72 + rng.next_val() * 0.22)
            local_x = math.cos(angle) * rx * radius
            local_y = math.sin(angle) * ry * radius
            anisotropy = 0.82 + rng.next_val() * 0.18
            outer.append({
                'x': cx + (local_x * math.cos(aspect_angle) - local_y * math.sin(aspect_angle)) * anisotropy,
                'y': cy + local_x * math.sin(aspect_angle) + local_y * math.cos(aspect_angle)
            })
        outer = translate_to_origin(outer)
        family = 'deep-lobed star'
    elif bnd_type in ['concave', 'free']:
        if bnd_type == 'free':
            family = rng.pick(['convex', 'concave', 'tshape', 'lobed'])
        else:
            family = 'non-convex radial'
        if family == 'convex':
            return make_boundary('convex', seed ^ 0x513, options)
        if family == 'tshape':
            return make_boundary('tshape', seed ^ 0x891, options)
        if family == 'lobed':
            return make_boundary('lobed', seed ^ 0xA71, options)
        count = rng.int_range(9, 13)
        cx, cy = 18, 14
        rx, ry = rng.int_range(15, 19), rng.int_range(11, 14)
        outer = []
        for i in range(count):
            angle = -math.pi/2 + (i / count) * 2 * math.pi + rng.next_val() * 0.08
            inset = (rng.next_val() * 0.22 + 0.48) if (i == 2 or i == math.floor(count * 0.58)) else (rng.next_val() * 0.18 + 0.82)
            outer.append({'x': cx + math.cos(angle) * rx * inset, 'y': cy + math.sin(angle) * ry * inset})
        outer = translate_to_origin(outer)
    else:
        w = rng.int_range(32, 38)
        h = rng.int_range(21, 27)
        outer = [{'x':0,'y':0},{'x':w,'y':0},{'x':w,'y':h},{'x':0,'y':h}]
    return {'outer': outer, 'seed': seed, 'type': bnd_type, 'family': family}

def atrium_candidates(boundary_data):
    b = bounds_of(boundary_data['outer'])
    center = polygon_centroid(boundary_data['outer'])
    w = b['maxX'] - b['minX']
    h = b['maxY'] - b['minY']
    
    # Procedural generation of arbitrary atrium polygons (avoiding simple hardcoded rectangles)
    # Generate irregular polygons around the centroid
    aw = clamp(round(w * 0.18), 4, 7)
    ah = clamp(round(h * 0.22), 4, 6)
    
    # 1) Irregular central atrium (e.g. L-shape or clipped shape)
    central = [
        {'x': round(center['x'] - aw/2), 'y': round(center['y'] - ah/2)},
        {'x': round(center['x'] + aw/2), 'y': round(center['y'] - ah/2)},
        {'x': round(center['x'] + aw/2), 'y': round(center['y'] + ah/3)},
        {'x': round(center['x'] + aw/4), 'y': round(center['y'] + ah/3)},
        {'x': round(center['x'] + aw/4), 'y': round(center['y'] + ah/2)},
        {'x': round(center['x'] - aw/2), 'y': round(center['y'] + ah/2)}
    ]
    # 2) Triangular/Trapezoidal atrium (Alternative)
    tri_atrium = [
        {'x': round(center['x'] - aw/2), 'y': round(center['y'] - ah/2)},
        {'x': round(center['x'] + aw/2), 'y': round(center['y'] - ah/2)},
        {'x': round(center['x']), 'y': round(center['y'] + ah/2)}
    ]
    
    def valid(hole):
        return polygon_inside_site(hole, boundary_data['outer'], [])
        
    return [
        { 'id': 'none', 'label': 'No atrium', 'holes': [] },
        { 'id': 'central', 'label': 'Irregular Atrium', 'holes': [central] if valid(central) else [] },
        { 'id': 'split', 'label': 'Triangular Lightcourt', 'holes': [tri_atrium] if valid(tri_atrium) else [] }
    ]

def build_site(boundary_data, holes):
    outer_bounds = bounds_of(boundary_data['outer'])
    cells = []
    cell_set = set()
    for y in range(math.floor(outer_bounds['minY']), math.ceil(outer_bounds['maxY'])):
        for x in range(math.floor(outer_bounds['minX']), math.ceil(outer_bounds['maxX'])):
            center = {'x': x + 0.5, 'y': y + 0.5}
            if not point_in_polygon(center, boundary_data['outer']):
                continue
            if any(point_in_polygon(center, hole) for hole in holes):
                continue
            cell = {'x': x, 'y': y}
            cells.append(cell)
            cell_set.add(key(x, y))
            
    # Distance Field Generator
    def make_distance_field(seed_predicate):
        field = {}
        queue = []
        for cell in cells:
            if seed_predicate(cell):
                k = key(cell['x'], cell['y'])
                field[k] = 0
                queue.append(cell)
        for idx in range(len(queue)):
            current = queue[idx]
            curr_k = key(current['x'], current['y'])
            next_dist = field[curr_k] + 1
            for dx, dy in [[1,0], [-1,0], [0,1], [0,-1]]:
                nx, ny = current['x'] + dx, current['y'] + dy
                nk = key(nx, ny)
                if nk not in cell_set or nk in field:
                    continue
                field[nk] = next_dist
                queue.append({'x': nx, 'y': ny})
        return field

    def touches_outer(cell):
        for dx, dy in [[1,0], [-1,0], [0,1], [0,-1]]:
            pt = {'x': cell['x'] + dx + 0.5, 'y': cell['y'] + dy + 0.5}
            if not point_in_polygon(pt, boundary_data['outer']) and not point_on_polygon(pt, boundary_data['outer']):
                return True
        return False

    def touches_atrium(cell):
        for hole in holes:
            for dx, dy in [[1,0], [-1,0], [0,1], [0,-1]]:
                pt = {'x': cell['x'] + dx + 0.5, 'y': cell['y'] + dy + 0.5}
                if point_in_polygon(pt, hole):
                    return True
        return False

    outer_distance = make_distance_field(touches_outer)
    atrium_distance = make_distance_field(touches_atrium) if holes else {}
    distance = make_distance_field(lambda c: touches_outer(c) or touches_atrium(c))
    
    return {
        'outer': boundary_data['outer'],
        'holes': holes,
        'cells': cells,
        'cellSet': cell_set,
        'distance': distance,
        'outerDistance': outer_distance,
        'atriumDistance': atrium_distance,
        'bounds': outer_bounds,
        'area': len(cells),
        'exactArea': polygon_area(boundary_data['outer']) - sum(polygon_area(hole) for hole in holes),
        'outerPerimeter': polygon_perimeter(boundary_data['outer']),
        'innerPerimeter': sum(polygon_perimeter(hole) for hole in holes),
        'reflexVertices': reflex_vertex_count(boundary_data['outer']),
        'convexityRatio': polygon_area(boundary_data['outer']) / max(EPSILON, polygon_area(convex_hull(boundary_data['outer'])))
    }

def get_shared_overlap(poly_a, poly_b):
    """
    Returns the total shared collinear edge overlap length between two polygons.
    Ensures that any segment sharing is at least 0.5m.
    """
    overlap_len = 0.0
    na = len(poly_a)
    nb = len(poly_b)
    for i in range(na):
        a1 = poly_a[i]
        a2 = poly_a[(i + 1) % na]
        # Edge segment vector
        ax, ay = a2['x'] - a1['x'], a2['y'] - a1['y']
        alen = math.hypot(ax, ay)
        if alen < EPSILON: continue
        
        for j in range(nb):
            b1 = poly_b[j]
            b2 = poly_b[(j + 1) % nb]
            bx, by = b2['x'] - b1['x'], b2['y'] - b1['y']
            blen = math.hypot(bx, by)
            if blen < EPSILON: continue
            
            # Check collinearity: cross product of directions
            cross = ax * by - ay * bx
            if abs(cross) / (alen * blen) > 0.05: # not parallel
                continue
                
            # Distance from b1/b2 to line a1-a2
            line_cross1 = (b1['x'] - a1['x']) * ay - (b1['y'] - a1['y']) * ax
            if abs(line_cross1) / alen > 0.05:
                continue
                
            # Collinear. Project endpoints to parameter range of line A
            # projection t = ((p - a1) . v) / |v|^2
            t_a1 = 0.0
            t_a2 = 1.0
            t_b1 = ((b1['x'] - a1['x']) * ax + (b1['y'] - a1['y']) * ay) / (alen * alen)
            t_b2 = ((b2['x'] - a1['x']) * ax + (b2['y'] - a1['y']) * ay) / (alen * alen)
            
            tb_min = min(t_b1, t_b2)
            tb_max = max(t_b1, t_b2)
            
            # Intersection of [0, 1] and [tb_min, tb_max]
            t_start = max(0.0, tb_min)
            t_end = min(1.0, tb_max)
            
            if t_end - t_start > 0.01:
                seg_overlap = (t_end - t_start) * alen
                if seg_overlap >= 0.5: # 0.5m overlap filter
                    overlap_len += seg_overlap
                    
    return overlap_len

def build_procedural_shape(sides, lengths, angles):
    """
    Builds a closed polygon from sides, edge lengths, and angles.
    Enforces minimum 40 degrees angle constraints.
    Returns poly verts if valid, else None.
    """
    if len(lengths) < sides - 1 or len(angles) < sides - 2:
        return None
    verts = [{'x': 0.0, 'y': 0.0}]
    curr_ang = 0.0
    for i in range(sides - 1):
        L = lengths[i]
        dx = L * math.cos(curr_ang)
        dy = L * math.sin(curr_ang)
        verts.append({'x': verts[-1]['x'] + dx, 'y': verts[-1]['y'] + dy})
        if i < sides - 2:
            # Internal angle -> turn angle
            turn = math.radians(180.0 - angles[i])
            curr_ang += turn
            
    # Close it
    p_last = verts[-1]
    dx_close = -p_last['x']
    dy_close = -p_last['y']
    L_close = math.hypot(dx_close, dy_close)
    if L_close < 0.5 or L_close > 30.0:
        return None
        
    # Snap closing length to nearest 0.5m
    grid_L = round(L_close * 2) / 2
    if abs(L_close - grid_L) > 0.05:
        return None
        
    # Calculate closing internal angles
    p_prev = verts[-2]
    v_in_dx, v_in_dy = p_last['x'] - p_prev['x'], p_last['y'] - p_prev['y']
    a_in = math.atan2(v_in_dy, v_in_dx)
    v_out_dx, v_out_dy = -p_last['x'], -p_last['y']
    a_out = math.atan2(v_out_dy, v_out_dx)
    ia_last = math.degrees(((a_out - a_in) % (2*math.pi) + 2*math.pi) % (2*math.pi))
    if ia_last > 180: ia_last = 360 - ia_last
    
    v_in_dx, v_in_dy = -p_last['x'], -p_last['y']
    a_in = math.atan2(v_in_dy, v_in_dx)
    p_1 = verts[1]
    v_out_dx, v_out_dy = p_1['x'], p_1['y']
    a_out = math.atan2(v_out_dy, v_out_dx)
    ia_first = math.degrees(((a_out - a_in) % (2*math.pi) + 2*math.pi) % (2*math.pi))
    if ia_first > 180: ia_first = 360 - ia_first
    
    all_angs = list(angles[:sides-2]) + [ia_last, ia_first]
    if any(ang < 40.0 or ang > 175.0 for ang in all_angs):
        return None
        
    # Simple polygon check
    n = len(verts)
    for i in range(n):
        for j in range(i+2, n):
            if i == 0 and j == n - 1: continue
            if proper_segments_intersect(verts[i], verts[(i+1)%n], verts[j], verts[(j+1)%n]):
                return None
                
    # Centering translation
    return translate_to_origin(verts)

def trace_boundaries(occupied_keys):
    """
    Traces the exterior envelope and interior court boundaries of the combined placed shapes.
    Takes a set of occupied cell coordinate keys e.g. {"3,4", "4,4"}.
    Returns a list of loops, where each loop is a list of coordinate dicts.
    """
    occupied_cells = set()
    for k in occupied_keys:
        try:
            x, y = map(int, k.split(','))
            occupied_cells.add((x, y))
        except:
            continue
            
    edges = []
    for (x, y) in occupied_cells:
        # Right (up: from (x+1, y) to (x+1, y+1))
        if (x + 1, y) not in occupied_cells:
            edges.append(((x + 1, y), (x + 1, y + 1)))
        # Top (left: from (x+1, y+1) to (x, y+1))
        if (x, y + 1) not in occupied_cells:
            edges.append(((x + 1, y + 1), (x, y + 1)))
        # Left (down: from (x, y+1) to (x, y))
        if (x - 1, y) not in occupied_cells:
            edges.append(((x, y + 1), (x, y)))
        # Bottom (right: from (x, y) to (x+1, y))
        if (x, y - 1) not in occupied_cells:
            edges.append(((x, y), (x + 1, y)))
            
    edges_set = set(edges)
    loops = []
    guard = 0
    while edges_set and guard < 10000:
        guard += 1
        start_edge = next(iter(edges_set))
        edges_set.remove(start_edge)
        
        loop = [start_edge[0], start_edge[1]]
        curr = start_edge[1]
        
        inner_guard = 0
        while inner_guard < len(edges) + 10:
            inner_guard += 1
            next_edge = None
            for e in edges_set:
                if e[0] == curr:
                    next_edge = e
                    break
            if next_edge:
                edges_set.remove(next_edge)
                loop.append(next_edge[1])
                curr = next_edge[1]
                if curr == loop[0]:
                    break
            else:
                break
                
        if len(loop) >= 4:
            loop_pts = [{'x': p[0], 'y': p[1]} for p in loop[:-1]]
            loops.append(loop_pts)
            
    return loops


