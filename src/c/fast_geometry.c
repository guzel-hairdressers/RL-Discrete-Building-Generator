#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>

/* Keep these values in lock-step with geometry.py. */
#define EPSILON 1.0e-9
#define COLLINEAR_EPSILON 1.0e-7
#define FAST_GEOMETRY_ABI_VERSION 3

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

enum SegmentIntersectionKind {
    SEGMENT_NONE = 0,
    SEGMENT_TOUCH = 1,
    SEGMENT_OVERLAP = 2,
    SEGMENT_PROPER = 3
};

int fast_geometry_abi_version(void) {
    return FAST_GEOMETRY_ABI_VERSION;
}

static inline double point_distance(Point first, Point second) {
    return hypot(second.x - first.x, second.y - first.y);
}

static inline double orientation(Point first, Point second, Point third) {
    return (second.x - first.x) * (third.y - first.y)
        - (second.y - first.y) * (third.x - first.x);
}

static inline BoundingBox get_bounds(const Point* poly, int count) {
    BoundingBox box = {poly[0].x, poly[0].y, poly[0].x, poly[0].y};
    for (int index = 1; index < count; ++index) {
        if (poly[index].x < box.minX) box.minX = poly[index].x;
        if (poly[index].x > box.maxX) box.maxX = poly[index].x;
        if (poly[index].y < box.minY) box.minY = poly[index].y;
        if (poly[index].y > box.maxY) box.maxY = poly[index].y;
    }
    return box;
}

static double signed_area(const Point* poly, int count) {
    long double cross_sum = 0.0L;
    for (int index = 0; index < count; ++index) {
        Point first = poly[index];
        Point second = poly[(index + 1) % count];
        cross_sum += (long double)first.x * (long double)second.y
            - (long double)second.x * (long double)first.y;
    }
    return (double)(0.5L * cross_sum);
}

static inline int point_on_segment(Point point, Point first, Point second) {
    double length = point_distance(first, second);
    if (length <= EPSILON) {
        return point_distance(point, first) <= COLLINEAR_EPSILON;
    }
    if (fabs(orientation(first, second, point)) > COLLINEAR_EPSILON * length) {
        return 0;
    }
    double dx = second.x - first.x;
    double dy = second.y - first.y;
    double dot = (point.x - first.x) * dx + (point.y - first.y) * dy;
    return dot >= -COLLINEAR_EPSILON
        && dot <= length * length + COLLINEAR_EPSILON;
}

static int point_on_polygon(Point point, const Point* poly, int count) {
    for (int index = 0; index < count; ++index) {
        if (point_on_segment(point, poly[index], poly[(index + 1) % count])) {
            return 1;
        }
    }
    return 0;
}

static int point_in_polygon(Point point, const Point* poly, int count) {
    if (count < 3) return 0;
    int inside = 0;
    Point previous = poly[count - 1];
    for (int index = 0; index < count; ++index) {
        Point current = poly[index];
        if ((current.y > point.y) != (previous.y > point.y)) {
            double crossing_x = current.x
                + (point.y - current.y) * (previous.x - current.x)
                    / (previous.y - current.y);
            if (point.x < crossing_x) inside = !inside;
        }
        previous = current;
    }
    return inside;
}

static inline int point_strictly_inside(Point point, const Point* poly, int count) {
    return !point_on_polygon(point, poly, count)
        && point_in_polygon(point, poly, count);
}

static int segments_collinear(Point first, Point second, Point third, Point fourth) {
    double first_length = point_distance(first, second);
    double second_length = point_distance(third, fourth);
    if (first_length <= EPSILON || second_length <= EPSILON) return 0;

    double direction_cross = fabs(
        (second.x - first.x) * (fourth.y - third.y)
        - (second.y - first.y) * (fourth.x - third.x)
    );
    if (direction_cross > COLLINEAR_EPSILON * first_length * second_length) {
        return 0;
    }
    return fabs(orientation(first, second, third))
            <= COLLINEAR_EPSILON * first_length
        && fabs(orientation(first, second, fourth))
            <= COLLINEAR_EPSILON * first_length
        && fabs(orientation(third, fourth, first))
            <= COLLINEAR_EPSILON * second_length
        && fabs(orientation(third, fourth, second))
            <= COLLINEAR_EPSILON * second_length;
}

static int tolerant_segments_collinear(
    Point first,
    Point second,
    Point third,
    Point fourth,
    double linear_tolerance,
    double angular_tolerance
) {
    double first_length = point_distance(first, second);
    double second_length = point_distance(third, fourth);
    if (first_length <= 1.0e-5 || second_length <= 1.0e-5) return 0;

    double direction_cross = fabs(
        (second.x - first.x) * (fourth.y - third.y)
        - (second.y - first.y) * (fourth.x - third.x)
    ) / (first_length * second_length);
    if (direction_cross > angular_tolerance) return 0;

    return fabs(orientation(first, second, third))
            <= linear_tolerance * first_length
        && fabs(orientation(first, second, fourth))
            <= linear_tolerance * first_length
        && fabs(orientation(third, fourth, first))
            <= linear_tolerance * second_length
        && fabs(orientation(third, fourth, second))
            <= linear_tolerance * second_length;
}

static int overlap_interval_on_first_tolerant(
    Point first,
    Point second,
    Point third,
    Point fourth,
    double tolerance,
    double* start,
    double* end
) {
    double dx = second.x - first.x;
    double dy = second.y - first.y;
    double length_squared = dx * dx + dy * dy;
    if (length_squared <= 1.0e-10) return 0;

    double third_parameter = (
        (third.x - first.x) * dx + (third.y - first.y) * dy
    ) / length_squared;
    double fourth_parameter = (
        (fourth.x - first.x) * dx + (fourth.y - first.y) * dy
    ) / length_squared;
    *start = fmax(0.0, fmin(third_parameter, fourth_parameter));
    *end = fmin(1.0, fmax(third_parameter, fourth_parameter));
    return (*end - *start) * sqrt(length_squared) > tolerance;
}

/* This mirrors geometry._collinear_overlap_length, including its symmetric
 * dominant-axis projection. */
static double collinear_overlap_length(
    Point first,
    Point second,
    Point third,
    Point fourth
) {
    Point points[4] = {first, second, third, fourth};
    double min_x = points[0].x;
    double max_x = points[0].x;
    double min_y = points[0].y;
    double max_y = points[0].y;
    int min_x_index = 0;
    int max_x_index = 0;
    int min_y_index = 0;
    int max_y_index = 0;
    for (int index = 1; index < 4; ++index) {
        if (points[index].x < min_x) {
            min_x = points[index].x;
            min_x_index = index;
        }
        if (points[index].x > max_x) {
            max_x = points[index].x;
            max_x_index = index;
        }
        if (points[index].y < min_y) {
            min_y = points[index].y;
            min_y_index = index;
        }
        if (points[index].y > max_y) {
            max_y = points[index].y;
            max_y_index = index;
        }
    }

    double span_x = max_x - min_x;
    double span_y = max_y - min_y;
    double coordinate_overlap;
    double scale;
    if (span_x >= span_y) {
        double first_min = fmin(first.x, second.x);
        double first_max = fmax(first.x, second.x);
        double second_min = fmin(third.x, fourth.x);
        double second_max = fmax(third.x, fourth.x);
        coordinate_overlap = fmin(first_max, second_max)
            - fmax(first_min, second_min);
        if (coordinate_overlap <= COLLINEAR_EPSILON) return 0.0;
        scale = point_distance(points[max_x_index], points[min_x_index])
            / fmax(EPSILON, fabs(max_x - min_x));
    } else {
        double first_min = fmin(first.y, second.y);
        double first_max = fmax(first.y, second.y);
        double second_min = fmin(third.y, fourth.y);
        double second_max = fmax(third.y, fourth.y);
        coordinate_overlap = fmin(first_max, second_max)
            - fmax(first_min, second_min);
        if (coordinate_overlap <= COLLINEAR_EPSILON) return 0.0;
        scale = point_distance(points[max_y_index], points[min_y_index])
            / fmax(EPSILON, fabs(max_y - min_y));
    }
    return coordinate_overlap * scale;
}

static enum SegmentIntersectionKind segment_intersection_kind(
    Point first,
    Point second,
    Point third,
    Point fourth
) {
    double first_orientation = orientation(first, second, third);
    double second_orientation = orientation(first, second, fourth);
    double third_orientation = orientation(third, fourth, first);
    double fourth_orientation = orientation(third, fourth, second);
    double scale = fmax(
        fmax(point_distance(first, second), point_distance(third, fourth)),
        1.0
    );
    double tolerance = COLLINEAR_EPSILON * scale;

    if (((first_orientation > tolerance && second_orientation < -tolerance)
            || (first_orientation < -tolerance && second_orientation > tolerance))
        && ((third_orientation > tolerance && fourth_orientation < -tolerance)
            || (third_orientation < -tolerance && fourth_orientation > tolerance))) {
        return SEGMENT_PROPER;
    }

    if (segments_collinear(first, second, third, fourth)) {
        if (collinear_overlap_length(first, second, third, fourth)
                > COLLINEAR_EPSILON) {
            return SEGMENT_OVERLAP;
        }
        if (point_on_segment(first, third, fourth)
            || point_on_segment(second, third, fourth)
            || point_on_segment(third, first, second)
            || point_on_segment(fourth, first, second)) {
            return SEGMENT_TOUCH;
        }
        return SEGMENT_NONE;
    }

    if ((fabs(first_orientation) <= tolerance
            && point_on_segment(third, first, second))
        || (fabs(second_orientation) <= tolerance
            && point_on_segment(fourth, first, second))
        || (fabs(third_orientation) <= tolerance
            && point_on_segment(first, third, fourth))
        || (fabs(fourth_orientation) <= tolerance
            && point_on_segment(second, third, fourth))) {
        return SEGMENT_TOUCH;
    }
    return SEGMENT_NONE;
}

static int is_simple_polygon(const Point* poly, int count) {
    if (count < 3) return 0;
    for (int index = 0; index < count; ++index) {
        if (!isfinite(poly[index].x) || !isfinite(poly[index].y)) return 0;
    }
    if (fabs(signed_area(poly, count)) <= EPSILON) return 0;
    for (int index = 0; index < count; ++index) {
        if (point_distance(poly[index], poly[(index + 1) % count]) <= EPSILON) {
            return 0;
        }
    }
    for (int first_index = 0; first_index < count; ++first_index) {
        Point first = poly[first_index];
        Point second = poly[(first_index + 1) % count];
        for (int second_index = first_index + 1; second_index < count; ++second_index) {
            if (second_index == (first_index + 1) % count) continue;
            if (first_index == (second_index + 1) % count) continue;
            Point third = poly[second_index];
            Point fourth = poly[(second_index + 1) % count];
            if (segment_intersection_kind(first, second, third, fourth)
                    != SEGMENT_NONE) {
                return 0;
            }
        }
    }
    return 1;
}

static int point_in_triangle_inclusive(
    Point point,
    Point first,
    Point second,
    Point third
) {
    double values[3] = {
        orientation(first, second, point),
        orientation(second, third, point),
        orientation(third, first, point)
    };
    int has_negative = 0;
    int has_positive = 0;
    for (int index = 0; index < 3; ++index) {
        if (values[index] < -EPSILON) has_negative = 1;
        if (values[index] > EPSILON) has_positive = 1;
    }
    return !(has_negative && has_positive);
}

static int polygon_representative_point(
    const Point* poly,
    int count,
    Point* result
) {
    double area_twice = 2.0 * signed_area(poly, count);
    if (fabs(area_twice) > EPSILON) {
        long double x_sum = 0.0L;
        long double y_sum = 0.0L;
        long double cross_sum = 0.0L;
        for (int index = 0; index < count; ++index) {
            Point first = poly[index];
            Point second = poly[(index + 1) % count];
            long double cross = (long double)first.x * second.y
                - (long double)second.x * first.y;
            cross_sum += cross;
            x_sum += ((long double)first.x + second.x) * cross;
            y_sum += ((long double)first.y + second.y) * cross;
        }
        if (fabsl(cross_sum) > EPSILON) {
            Point centroid = {
                (double)(x_sum / (3.0L * cross_sum)),
                (double)(y_sum / (3.0L * cross_sum))
            };
            if (point_strictly_inside(centroid, poly, count)) {
                *result = centroid;
                return 1;
            }
        }
    }

    double winding = signed_area(poly, count) >= 0.0 ? 1.0 : -1.0;
    double best_area = -1.0;
    Point best = {0.0, 0.0};
    for (int index = 0; index < count; ++index) {
        Point first = poly[(index + count - 1) % count];
        Point second = poly[index];
        Point third = poly[(index + 1) % count];
        double triangle_area = winding * orientation(first, second, third);
        if (triangle_area <= EPSILON) continue;
        int contains_vertex = 0;
        for (int other_index = 0; other_index < count; ++other_index) {
            if (other_index == index
                || other_index == (index + count - 1) % count
                || other_index == (index + 1) % count) {
                continue;
            }
            if (point_in_triangle_inclusive(
                    poly[other_index], first, second, third)) {
                contains_vertex = 1;
                break;
            }
        }
        if (contains_vertex) continue;
        Point candidate = {
            (first.x + second.x + third.x) / 3.0,
            (first.y + second.y + third.y) / 3.0
        };
        if (triangle_area > best_area
            && point_strictly_inside(candidate, poly, count)) {
            best_area = triangle_area;
            best = candidate;
        }
    }
    if (best_area > 0.0) {
        *result = best;
        return 1;
    }
    return 0;
}

int polygons_overlap_c(
    const Point* first_poly,
    int first_count,
    const Point* second_poly,
    int second_count
) {
    if (first_count < 3 || second_count < 3) return 0;

    BoundingBox first_box = get_bounds(first_poly, first_count);
    BoundingBox second_box = get_bounds(second_poly, second_count);
    if (first_box.maxX <= second_box.minX + EPSILON
        || second_box.maxX <= first_box.minX + EPSILON
        || first_box.maxY <= second_box.minY + EPSILON
        || second_box.maxY <= first_box.minY + EPSILON) {
        return 0;
    }

    for (int first_index = 0; first_index < first_count; ++first_index) {
        Point first = first_poly[first_index];
        Point second = first_poly[(first_index + 1) % first_count];
        for (int second_index = 0; second_index < second_count; ++second_index) {
            Point third = second_poly[second_index];
            Point fourth = second_poly[(second_index + 1) % second_count];
            if (segment_intersection_kind(first, second, third, fourth)
                    == SEGMENT_PROPER) {
                return 1;
            }
        }
    }

    for (int index = 0; index < first_count; ++index) {
        if (point_strictly_inside(first_poly[index], second_poly, second_count)) {
            return 1;
        }
    }
    for (int index = 0; index < second_count; ++index) {
        if (point_strictly_inside(second_poly[index], first_poly, first_count)) {
            return 1;
        }
    }

    for (int index = 0; index < first_count; ++index) {
        Point first = first_poly[index];
        Point second = first_poly[(index + 1) % first_count];
        Point midpoint = {(first.x + second.x) / 2.0, (first.y + second.y) / 2.0};
        if (point_strictly_inside(midpoint, second_poly, second_count)) return 1;
    }
    for (int index = 0; index < second_count; ++index) {
        Point first = second_poly[index];
        Point second = second_poly[(index + 1) % second_count];
        Point midpoint = {(first.x + second.x) / 2.0, (first.y + second.y) / 2.0};
        if (point_strictly_inside(midpoint, first_poly, first_count)) return 1;
    }

    Point representative;
    if (polygon_representative_point(first_poly, first_count, &representative)
        && point_strictly_inside(representative, second_poly, second_count)) {
        return 1;
    }
    if (polygon_representative_point(second_poly, second_count, &representative)
        && point_strictly_inside(representative, first_poly, first_count)) {
        return 1;
    }

    double first_winding = signed_area(first_poly, first_count);
    double second_winding = signed_area(second_poly, second_count);
    for (int first_index = 0; first_index < first_count; ++first_index) {
        Point first = first_poly[first_index];
        Point second = first_poly[(first_index + 1) % first_count];
        double first_dx = second.x - first.x;
        double first_dy = second.y - first.y;
        double first_length = hypot(first_dx, first_dy);
        if (first_length <= EPSILON) continue;
        double first_sign = first_winding >= 0.0 ? 1.0 : -1.0;
        double first_normal_x = -first_sign * first_dy / first_length;
        double first_normal_y = first_sign * first_dx / first_length;

        for (int second_index = 0; second_index < second_count; ++second_index) {
            Point third = second_poly[second_index];
            Point fourth = second_poly[(second_index + 1) % second_count];
            if (!segments_collinear(first, second, third, fourth)) continue;
            if (collinear_overlap_length(first, second, third, fourth)
                    <= COLLINEAR_EPSILON) {
                continue;
            }
            double second_dx = fourth.x - third.x;
            double second_dy = fourth.y - third.y;
            double second_length = hypot(second_dx, second_dy);
            if (second_length <= EPSILON) continue;
            double second_sign = second_winding >= 0.0 ? 1.0 : -1.0;
            double second_normal_x = -second_sign * second_dy / second_length;
            double second_normal_y = second_sign * second_dx / second_length;
            if (first_normal_x * second_normal_x
                    + first_normal_y * second_normal_y > 1.0 - 1.0e-6) {
                return 1;
            }
        }
    }
    return 0;
}

static int compare_double(const void* left, const void* right) {
    double first = *(const double*)left;
    double second = *(const double*)right;
    return (first > second) - (first < second);
}

static int append_segment_parameters(
    Point first,
    Point second,
    const Point* outer,
    int outer_count,
    double* values
) {
    double direction_x = second.x - first.x;
    double direction_y = second.y - first.y;
    double length_squared = direction_x * direction_x + direction_y * direction_y;
    int value_count = 0;
    values[value_count++] = 0.0;
    values[value_count++] = 1.0;
    if (length_squared <= EPSILON) return value_count;

    for (int index = 0; index < outer_count; ++index) {
        Point third = outer[index];
        Point fourth = outer[(index + 1) % outer_count];
        double other_x = fourth.x - third.x;
        double other_y = fourth.y - third.y;
        double denominator = direction_x * other_y - direction_y * other_x;
        double offset_x = third.x - first.x;
        double offset_y = third.y - first.y;
        if (fabs(denominator) > EPSILON) {
            double parameter = (offset_x * other_y - offset_y * other_x)
                / denominator;
            double other_parameter = (
                offset_x * direction_y - offset_y * direction_x
            ) / denominator;
            if (parameter >= -COLLINEAR_EPSILON
                && parameter <= 1.0 + COLLINEAR_EPSILON
                && other_parameter >= -COLLINEAR_EPSILON
                && other_parameter <= 1.0 + COLLINEAR_EPSILON) {
                values[value_count++] = fmax(0.0, fmin(1.0, parameter));
            }
        } else if (segments_collinear(first, second, third, fourth)) {
            Point endpoints[2] = {third, fourth};
            for (int endpoint_index = 0; endpoint_index < 2; ++endpoint_index) {
                Point point = endpoints[endpoint_index];
                double parameter = (
                    (point.x - first.x) * direction_x
                    + (point.y - first.y) * direction_y
                ) / length_squared;
                if (parameter >= -COLLINEAR_EPSILON
                    && parameter <= 1.0 + COLLINEAR_EPSILON) {
                    values[value_count++] = fmax(0.0, fmin(1.0, parameter));
                }
            }
        }
    }
    qsort(values, (size_t)value_count, sizeof(double), compare_double);
    int unique_count = 0;
    for (int index = 0; index < value_count; ++index) {
        if (unique_count == 0
            || fabs(values[index] - values[unique_count - 1])
                > COLLINEAR_EPSILON) {
            values[unique_count++] = values[index];
        }
    }
    return unique_count;
}

int polygon_inside_site_c(
    const Point* poly,
    int count,
    const Point* outer,
    int outer_count,
    const Point* holes_flat,
    const int* hole_counts,
    int hole_count
) {
    if (!is_simple_polygon(poly, count) || outer_count < 3) return 0;

    for (int index = 0; index < count; ++index) {
        if (!point_in_polygon(poly[index], outer, outer_count)
            && !point_on_polygon(poly[index], outer, outer_count)) {
            return 0;
        }
    }

    size_t parameter_capacity = (size_t)(2 * outer_count + 2);
    double* parameters = (double*)malloc(parameter_capacity * sizeof(double));
    if (parameters == NULL) return 0;
    for (int index = 0; index < count; ++index) {
        Point first = poly[index];
        Point second = poly[(index + 1) % count];
        int parameter_count = append_segment_parameters(
            first, second, outer, outer_count, parameters
        );
        for (int parameter_index = 0;
                parameter_index + 1 < parameter_count;
                ++parameter_index) {
            double start = parameters[parameter_index];
            double end = parameters[parameter_index + 1];
            if (end - start <= EPSILON) continue;
            double parameter = (start + end) / 2.0;
            Point sample = {
                first.x + (second.x - first.x) * parameter,
                first.y + (second.y - first.y) * parameter
            };
            if (!point_in_polygon(sample, outer, outer_count)
                && !point_on_polygon(sample, outer, outer_count)) {
                free(parameters);
                return 0;
            }
        }
    }
    free(parameters);

    int offset = 0;
    for (int index = 0; index < hole_count; ++index) {
        int current_count = hole_counts[index];
        if (polygons_overlap_c(
                poly, count, holes_flat + offset, current_count)) {
            return 0;
        }
        offset += current_count;
    }
    return 1;
}

int symmetric_segment_overlap_c(
    Point first,
    Point second,
    Point third,
    Point fourth,
    double linear_tolerance,
    double angular_tolerance,
    double* first_start,
    double* first_end,
    double* second_start,
    double* second_end,
    double* shared_length
) {
    if (!tolerant_segments_collinear(
            first,
            second,
            third,
            fourth,
            linear_tolerance,
            angular_tolerance)) {
        return 0;
    }
    if (!overlap_interval_on_first_tolerant(
            first,
            second,
            third,
            fourth,
            linear_tolerance,
            first_start,
            first_end)
        || !overlap_interval_on_first_tolerant(
            third,
            fourth,
            first,
            second,
            linear_tolerance,
            second_start,
            second_end)) {
        return 0;
    }
    double first_overlap = (*first_end - *first_start)
        * point_distance(first, second);
    double second_overlap = (*second_end - *second_start)
        * point_distance(third, fourth);
    *shared_length = fmin(first_overlap, second_overlap);
    return 1;
}

double point_to_segments_distance_c(
    Point point,
    const Point* segment_endpoints,
    int segment_count
) {
    double best = INFINITY;
    for (int index = 0; index < segment_count; ++index) {
        Point first = segment_endpoints[index * 2];
        Point second = segment_endpoints[index * 2 + 1];
        double dx = second.x - first.x;
        double dy = second.y - first.y;
        double length_squared = dx * dx + dy * dy;
        double distance;
        if (length_squared <= EPSILON) {
            distance = point_distance(point, first);
        } else {
            double parameter = (
                (point.x - first.x) * dx + (point.y - first.y) * dy
            ) / length_squared;
            parameter = fmax(0.0, fmin(1.0, parameter));
            Point projection = {
                first.x + parameter * dx,
                first.y + parameter * dy
            };
            distance = point_distance(point, projection);
        }
        if (distance < best) best = distance;
    }
    return best;
}

void shared_overlap_pair_c(
    const Point* first_poly,
    int first_count,
    const Point* second_poly,
    int second_count,
    double* maximum_overlap,
    double* total_overlap
) {
    double maximum = 0.0;
    int capacity = first_count > 0 && second_count > 0
        ? first_count * second_count
        : 0;
    double* overlaps = capacity > 0
        ? (double*)malloc((size_t)capacity * sizeof(double))
        : NULL;
    int overlap_count = 0;

    if (first_count >= 3 && second_count >= 3) {
        for (int first_index = 0; first_index < first_count; ++first_index) {
            Point first = first_poly[first_index];
            Point second = first_poly[(first_index + 1) % first_count];
            for (int second_index = 0; second_index < second_count; ++second_index) {
                Point third = second_poly[second_index];
                Point fourth = second_poly[(second_index + 1) % second_count];
                if (!segments_collinear(first, second, third, fourth)) continue;
                double overlap = collinear_overlap_length(
                    first, second, third, fourth
                );
                if (overlap <= COLLINEAR_EPSILON) continue;
                if (overlap > maximum) maximum = overlap;
                if (overlaps != NULL) overlaps[overlap_count++] = overlap;
            }
        }
    }

    long double total = 0.0L;
    if (overlaps != NULL) {
        qsort(overlaps, (size_t)overlap_count, sizeof(double), compare_double);
        for (int index = 0; index < overlap_count; ++index) {
            total += (long double)overlaps[index];
        }
        free(overlaps);
    }
    *maximum_overlap = maximum;
    *total_overlap = (double)total;
}

double get_shared_overlap_c(
    const Point* first_poly,
    int first_count,
    const Point* second_poly,
    int second_count
) {
    double maximum = 0.0;
    double total = 0.0;
    shared_overlap_pair_c(
        first_poly,
        first_count,
        second_poly,
        second_count,
        &maximum,
        &total
    );
    return total;
}

int polygons_overlap_translated_c(
    const Point* first_poly,
    int first_count,
    double dx,
    double dy,
    const Point* second_poly,
    int second_count
) {
    if (first_count < 3 || second_count < 3) return 0;
    if (first_count <= 64) {
        Point local_first[64];
        for (int i = 0; i < first_count; ++i) {
            local_first[i].x = first_poly[i].x + dx;
            local_first[i].y = first_poly[i].y + dy;
        }
        return polygons_overlap_c(local_first, first_count, second_poly, second_count);
    }
    Point* dynamic_first = (Point*)malloc((size_t)first_count * sizeof(Point));
    if (!dynamic_first) return 0;
    for (int i = 0; i < first_count; ++i) {
        dynamic_first[i].x = first_poly[i].x + dx;
        dynamic_first[i].y = first_poly[i].y + dy;
    }
    int result = polygons_overlap_c(dynamic_first, first_count, second_poly, second_count);
    free(dynamic_first);
    return result;
}

int polygon_inside_site_translated_c(
    const Point* poly,
    int count,
    double dx,
    double dy,
    const Point* outer,
    int outer_count,
    const Point* holes_flat,
    const int* hole_counts,
    int hole_count
) {
    if (count < 3 || outer_count < 3) return 0;
    if (count <= 64) {
        Point local_poly[64];
        for (int i = 0; i < count; ++i) {
            local_poly[i].x = poly[i].x + dx;
            local_poly[i].y = poly[i].y + dy;
        }
        return polygon_inside_site_c(local_poly, count, outer, outer_count, holes_flat, hole_counts, hole_count);
    }
    Point* dynamic_poly = (Point*)malloc((size_t)count * sizeof(Point));
    if (!dynamic_poly) return 0;
    for (int i = 0; i < count; ++i) {
        dynamic_poly[i].x = poly[i].x + dx;
        dynamic_poly[i].y = poly[i].y + dy;
    }
    int result = polygon_inside_site_c(dynamic_poly, count, outer, outer_count, holes_flat, hole_counts, hole_count);
    free(dynamic_poly);
    return result;
}

typedef struct {
    double min_x;
    double min_y;
    double max_x;
    double max_y;
    int shape_type;
    int cell_count;
} WFCRoomResult;

int tessellate_bay_wfc_c(
    const uint8_t* grid,
    int rows,
    int cols,
    double min_x,
    double min_y,
    double grid_pitch,
    WFCRoomResult* out_results,
    int max_results
) {
    if (!grid || rows <= 0 || cols <= 0 || !out_results || max_results <= 0) return 0;
    
    int total_cells = rows * cols;
    uint8_t* occupied = (uint8_t*)calloc((size_t)total_cells, sizeof(uint8_t));
    if (!occupied) return 0;
    
    int result_count = 0;
    
    for (int r = 0; r < rows; ++r) {
        for (int c = 0; c < cols; ++c) {
            int idx = r * cols + c;
            if (grid[idx] && !occupied[idx]) {
                if (result_count >= max_results) break;
                
                // 1. Try 2x2 large quad
                if (r + 1 < rows && c + 1 < cols &&
                    grid[idx + 1] && !occupied[idx + 1] &&
                    grid[idx + cols] && !occupied[idx + cols] &&
                    grid[idx + cols + 1] && !occupied[idx + cols + 1]) {
                    
                    occupied[idx] = 1;
                    occupied[idx + 1] = 1;
                    occupied[idx + cols] = 1;
                    occupied[idx + cols + 1] = 1;
                    
                    out_results[result_count].min_x = min_x + c * grid_pitch;
                    out_results[result_count].min_y = min_y + r * grid_pitch;
                    out_results[result_count].max_x = min_x + (c + 2) * grid_pitch;
                    out_results[result_count].max_y = min_y + (r + 2) * grid_pitch;
                    out_results[result_count].shape_type = 3;
                    out_results[result_count].cell_count = 4;
                    result_count++;
                    continue;
                }
                
                // 2. Try 1x3 horizontal
                if (c + 2 < cols &&
                    grid[idx + 1] && !occupied[idx + 1] &&
                    grid[idx + 2] && !occupied[idx + 2]) {
                    
                    occupied[idx] = 1;
                    occupied[idx + 1] = 1;
                    occupied[idx + 2] = 1;
                    
                    out_results[result_count].min_x = min_x + c * grid_pitch;
                    out_results[result_count].min_y = min_y + r * grid_pitch;
                    out_results[result_count].max_x = min_x + (c + 3) * grid_pitch;
                    out_results[result_count].max_y = min_y + (r + 1) * grid_pitch;
                    out_results[result_count].shape_type = 4;
                    out_results[result_count].cell_count = 3;
                    result_count++;
                    continue;
                }
                
                // 3. Try 3x1 vertical
                if (r + 2 < rows &&
                    grid[idx + cols] && !occupied[idx + cols] &&
                    grid[idx + 2 * cols] && !occupied[idx + 2 * cols]) {
                    
                    occupied[idx] = 1;
                    occupied[idx + cols] = 1;
                    occupied[idx + 2 * cols] = 1;
                    
                    out_results[result_count].min_x = min_x + c * grid_pitch;
                    out_results[result_count].min_y = min_y + r * grid_pitch;
                    out_results[result_count].max_x = min_x + (c + 1) * grid_pitch;
                    out_results[result_count].max_y = min_y + (r + 3) * grid_pitch;
                    out_results[result_count].shape_type = 5;
                    out_results[result_count].cell_count = 3;
                    result_count++;
                    continue;
                }
                
                // 4. Try 1x2 horizontal
                if (c + 1 < cols && grid[idx + 1] && !occupied[idx + 1]) {
                    occupied[idx] = 1;
                    occupied[idx + 1] = 1;
                    
                    out_results[result_count].min_x = min_x + c * grid_pitch;
                    out_results[result_count].min_y = min_y + r * grid_pitch;
                    out_results[result_count].max_x = min_x + (c + 2) * grid_pitch;
                    out_results[result_count].max_y = min_y + (r + 1) * grid_pitch;
                    out_results[result_count].shape_type = 1;
                    out_results[result_count].cell_count = 2;
                    result_count++;
                    continue;
                }
                
                // 5. Try 2x1 vertical
                if (r + 1 < rows && grid[idx + cols] && !occupied[idx + cols]) {
                    occupied[idx] = 1;
                    occupied[idx + cols] = 1;
                    
                    out_results[result_count].min_x = min_x + c * grid_pitch;
                    out_results[result_count].min_y = min_y + r * grid_pitch;
                    out_results[result_count].max_x = min_x + (c + 1) * grid_pitch;
                    out_results[result_count].max_y = min_y + (r + 2) * grid_pitch;
                    out_results[result_count].shape_type = 2;
                    out_results[result_count].cell_count = 2;
                    result_count++;
                    continue;
                }
                
                // 6. Fallback 1x1 cell
                occupied[idx] = 1;
                out_results[result_count].min_x = min_x + c * grid_pitch;
                out_results[result_count].min_y = min_y + r * grid_pitch;
                out_results[result_count].max_x = min_x + (c + 1) * grid_pitch;
                out_results[result_count].max_y = min_y + (r + 1) * grid_pitch;
                out_results[result_count].shape_type = 0;
                out_results[result_count].cell_count = 1;
                result_count++;
            }
        }
    }
    
    free(occupied);
    return result_count;
}


