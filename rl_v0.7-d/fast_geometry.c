#include <math.h>
#include <stdbool.h>
#include <stdlib.h>

#define EPSILON 1e-8
#define COLLINEAR_EPSILON 1e-7

typedef struct {
    double x;
    double y;
} Point;

typedef struct {
    double minX;
    double minY;
    double maxX;
    double maxY;
} BoundingBox;

static inline BoundingBox get_bounds(const Point* poly, int count) {
    BoundingBox box = {poly[0].x, poly[0].y, poly[0].x, poly[0].y};
    for (int i = 1; i < count; i++) {
        if (poly[i].x < box.minX) box.minX = poly[i].x;
        if (poly[i].x > box.maxX) box.maxX = poly[i].x;
        if (poly[i].y < box.minY) box.minY = poly[i].y;
        if (poly[i].y > box.maxY) box.maxY = poly[i].y;
    }
    return box;
}

static inline double cross_product(Point a, Point b, Point c) {
    return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
}

static inline int point_in_polygon_c(Point pt, const Point* poly, int count) {
    if (count < 3) return 0;
    int inside = 0;
    int prev_idx = count - 1;
    for (int curr_idx = 0; curr_idx < count; curr_idx++) {
        Point curr = poly[curr_idx];
        Point prev = poly[prev_idx];
        if ((curr.y > pt.y) != (prev.y > pt.y)) {
            double crossing_x = curr.x + ((pt.y - curr.y) * (prev.x - curr.x) / (prev.y - curr.y));
            if (pt.x < crossing_x) {
                inside = !inside;
            }
        }
        prev_idx = curr_idx;
    }
    return inside;
}

static inline int point_on_segment(Point p, Point a, Point b) {
    double min_x = a.x < b.x ? a.x : b.x;
    double max_x = a.x > b.x ? a.x : b.x;
    if (p.x < min_x - COLLINEAR_EPSILON || p.x > max_x + COLLINEAR_EPSILON) return 0;

    double min_y = a.y < b.y ? a.y : b.y;
    double max_y = a.y > b.y ? a.y : b.y;
    if (p.y < min_y - COLLINEAR_EPSILON || p.y > max_y + COLLINEAR_EPSILON) return 0;

    double cross = (p.y - a.y) * (b.x - a.x) - (p.x - a.x) * (b.y - a.y);
    if (fabs(cross) > EPSILON) return 0;
    double dot = (p.x - a.x) * (b.x - a.x) + (p.y - a.y) * (b.y - a.y);
    if (dot < -EPSILON) return 0;
    double len_sq = (b.x - a.x) * (b.x - a.x) + (b.y - a.y) * (b.y - a.y);
    if (dot > len_sq + EPSILON) return 0;
    return 1;
}

static inline int point_on_polygon_c(Point pt, const Point* poly, int count) {
    for (int i = 0; i < count; i++) {
        Point a = poly[i];
        Point b = poly[(i + 1) % count];
        if (point_on_segment(pt, a, b)) return 1;
    }
    return 0;
}

static inline int point_strictly_inside_c(Point pt, const Point* poly, int count) {
    return !point_on_polygon_c(pt, poly, count) && point_in_polygon_c(pt, poly, count);
}

static inline int segment_intersection_proper(Point a, Point b, Point c, Point d) {
    double cp1 = cross_product(a, b, c);
    double cp2 = cross_product(a, b, d);
    double cp3 = cross_product(c, d, a);
    double cp4 = cross_product(c, d, b);

    if (((cp1 > EPSILON && cp2 < -EPSILON) || (cp1 < -EPSILON && cp2 > EPSILON)) &&
        ((cp3 > EPSILON && cp4 < -EPSILON) || (cp3 < -EPSILON && cp4 > EPSILON))) {
        return 1;
    }
    return 0;
}

static inline double signed_area(const Point* poly, int count) {
    double area = 0.0;
    for (int i = 0; i < count; i++) {
        Point curr = poly[i];
        Point next = poly[(i + 1) % count];
        area += (curr.x * next.y - next.x * curr.y);
    }
    return area * 0.5;
}

static inline int segments_collinear(Point a, Point b, Point c, Point d) {
    if (fabs(cross_product(a, b, c)) > EPSILON) return 0;
    if (fabs(cross_product(a, b, d)) > EPSILON) return 0;
    return 1;
}

static inline double collinear_overlap_length(Point a, Point b, Point c, Point d) {
    double dx = b.x - a.x;
    double dy = b.y - a.y;
    double len_sq = dx * dx + dy * dy;
    if (len_sq <= EPSILON) return 0.0;
    double t_c = ((c.x - a.x) * dx + (c.y - a.y) * dy) / len_sq;
    double t_d = ((d.x - a.x) * dx + (d.y - a.y) * dy) / len_sq;
    double start = t_c < t_d ? t_c : t_d;
    double end = t_c > t_d ? t_c : t_d;
    if (start < 0.0) start = 0.0;
    if (end > 1.0) end = 1.0;
    if (end <= start + EPSILON) return 0.0;
    return (end - start) * sqrt(len_sq);
}

int polygons_overlap_c(const Point* poly1, int n1, const Point* poly2, int n2) {
    if (n1 < 3 || n2 < 3) return 0;

    BoundingBox b1 = get_bounds(poly1, n1);
    BoundingBox b2 = get_bounds(poly2, n2);

    if (b1.maxX <= b2.minX + EPSILON || b2.maxX <= b1.minX + EPSILON ||
        b1.maxY <= b2.minY + EPSILON || b2.maxY <= b1.minY + EPSILON) {
        return 0;
    }

    // 1. Edge-edge proper intersections
    for (int i = 0; i < n1; i++) {
        Point a = poly1[i];
        Point b = poly1[(i + 1) % n1];
        for (int j = 0; j < n2; j++) {
            Point c = poly2[j];
            Point d = poly2[(j + 1) % n2];
            if (segment_intersection_proper(a, b, c, d)) return 1;
        }
    }

    // 2. Vertex strictly inside check
    for (int i = 0; i < n1; i++) {
        if (point_strictly_inside_c(poly1[i], poly2, n2)) return 1;
    }
    for (int j = 0; j < n2; j++) {
        if (point_strictly_inside_c(poly2[j], poly1, n1)) return 1;
    }

    // 3. Edge midpoint strictly inside check
    for (int i = 0; i < n1; i++) {
        Point mid = {(poly1[i].x + poly1[(i + 1) % n1].x) * 0.5, (poly1[i].y + poly1[(i + 1) % n1].y) * 0.5};
        if (point_strictly_inside_c(mid, poly2, n2)) return 1;
    }
    for (int j = 0; j < n2; j++) {
        Point mid = {(poly2[j].x + poly2[(j + 1) % n2].x) * 0.5, (poly2[j].y + poly2[(j + 1) % n2].y) * 0.5};
        if (point_strictly_inside_c(mid, poly1, n1)) return 1;
    }

    // 4. Coincident edge checking (e.g. identical polygons)
    double w1 = signed_area(poly1, n1);
    double w2 = signed_area(poly2, n2);
    for (int i = 0; i < n1; i++) {
        Point a = poly1[i];
        Point b = poly1[(i + 1) % n1];
        double edge_dx = b.x - a.x;
        double edge_dy = b.y - a.y;
        double len = sqrt(edge_dx * edge_dx + edge_dy * edge_dy);
        if (len <= EPSILON) continue;
        double nx1 = (w1 >= 0.0) ? -edge_dy / len : edge_dy / len;
        double ny1 = (w1 >= 0.0) ? edge_dx / len : -edge_dx / len;

        for (int j = 0; j < n2; j++) {
            Point c = poly2[j];
            Point d = poly2[(j + 1) % n2];
            if (!segments_collinear(a, b, c, d)) continue;
            if (collinear_overlap_length(a, b, c, d) <= COLLINEAR_EPSILON) continue;

            double c_dx = d.x - c.x;
            double c_dy = d.y - c.y;
            double c_len = sqrt(c_dx * c_dx + c_dy * c_dy);
            if (c_len <= EPSILON) continue;
            double nx2 = (w2 >= 0.0) ? -c_dy / c_len : c_dy / c_len;
            double ny2 = (w2 >= 0.0) ? c_dx / c_len : -c_dx / c_len;

            if (nx1 * nx2 + ny1 * ny2 > 0.5) return 1;
        }
    }

    return 0;
}

// C implementation of polygon_inside_site
int polygon_inside_site_c(
    const Point* poly, int n,
    const Point* outer, int n_outer,
    const Point* holes_flat, const int* hole_counts, int num_holes
) {
    if (n < 3 || n_outer < 3) return 0;

    // 1. All vertices must be inside or on outer boundary
    for (int i = 0; i < n; i++) {
        Point pt = poly[i];
        if (!point_in_polygon_c(pt, outer, n_outer) && !point_on_polygon_c(pt, outer, n_outer)) {
            return 0;
        }
    }

    // 2. Segment midpoints against outer
    for (int i = 0; i < n; i++) {
        Point p1 = poly[i];
        Point p2 = poly[(i + 1) % n];
        Point mid = {(p1.x + p2.x) * 0.5, (p1.y + p2.y) * 0.5};
        if (!point_in_polygon_c(mid, outer, n_outer) && !point_on_polygon_c(mid, outer, n_outer)) {
            return 0;
        }
    }

    // 3. Holes overlap check
    int offset = 0;
    for (int h = 0; h < num_holes; h++) {
        int h_count = hole_counts[h];
        const Point* hole_poly = &holes_flat[offset];
        if (polygons_overlap_c(poly, n, hole_poly, h_count)) {
            return 0;
        }
        offset += h_count;
    }

    return 1;
}

double get_shared_overlap_c(const Point* poly1, int n1, const Point* poly2, int n2) {
    if (n1 < 3 || n2 < 3) return 0.0;
    double total = 0.0;
    for (int i = 0; i < n1; i++) {
        Point a = poly1[i];
        Point b = poly1[(i + 1) % n1];
        for (int j = 0; j < n2; j++) {
            Point c = poly2[j];
            Point d = poly2[(j + 1) % n2];
            if (segments_collinear(a, b, c, d)) {
                double overlap = collinear_overlap_length(a, b, c, d);
                if (overlap > COLLINEAR_EPSILON) {
                    total += overlap;
                }
            }
        }
    }
    return total;
}

void shared_overlap_pair_c(const Point* poly1, int n1, const Point* poly2, int n2, double* max_ovlp, double* total_ovlp) {
    double max_o = 0.0;
    double total_o = 0.0;
    if (n1 >= 3 && n2 >= 3) {
        for (int i = 0; i < n1; i++) {
            Point a = poly1[i];
            Point b = poly1[(i + 1) % n1];
            for (int j = 0; j < n2; j++) {
                Point c = poly2[j];
                Point d = poly2[(j + 1) % n2];
                if (segments_collinear(a, b, c, d)) {
                    double overlap = collinear_overlap_length(a, b, c, d);
                    if (overlap > COLLINEAR_EPSILON) {
                        if (overlap > max_o) max_o = overlap;
                        total_o += overlap;
                    }
                }
            }
        }
    }
    *max_ovlp = max_o;
    *total_ovlp = total_o;
}

