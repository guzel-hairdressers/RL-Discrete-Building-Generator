"""
Browse Database — CLI tool and local dashboard for browsing and visualizing
collected urban context sites.

Commands:
    python browse_database.py list                       # List all sites
    python browse_database.py list --city tokyo          # Filter by city
    python browse_database.py list --tier very_high      # Filter by density tier
    python browse_database.py list --sort building_count # Sort by field
    python browse_database.py view site_0001             # 3D visualize a site
    python browse_database.py stats                      # Aggregate statistics
    python browse_database.py dashboard                  # Open HTML dashboard
"""

import argparse
import json
import os
import sys
import webbrowser
import numpy as np

from site_database import list_sites, load_site, get_stats, DATABASE_DIR, SITES_DIR
from geometry_3d import extrude_polygon_to_3d_mesh, ensure_ccw_polygon


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")


def handle_list(args):
    """Print a table of all sites with key metrics."""
    sites = list_sites(
        sort_by=args.sort,
        descending=not args.ascending,
        density_tier=args.tier,
        city=args.city,
        typology=args.typology,
    )

    if not sites:
        print("No sites found in database.")
        return

    # Print table header
    print(f"\n{'ID':<12} {'City':<15} {'Zone':<18} {'Typology':<12} "
          f"{'Tier':<10} {'AreaTier':<9} {'Area(m²)':>9} {'FAR':>6} {'Bldgs':>6} "
          f"{'MaxH':>7}")
    print("-" * 115)

    for s in sites:
        atier = s.get('area_tier', 'M')
        area = s.get('site_area_m2', 0.0)
        print(f"{s['id']:<12} {s['city']:<15} {s['zone']:<18} {s['typology']:<12} "
              f"{s['density_tier']:<10} {atier:<9} {area:>9.1f} {s['far']:>6.1f} "
              f"{s['building_count']:>6d} {s['max_height']:>7.1f}")

    print(f"\nTotal: {len(sites)} sites")


def handle_view(args):
    """Load a site and render its 3D visualization."""
    site_id = args.site_id
    if not site_id.startswith("site_"):
        site_id = f"site_{site_id}"

    try:
        site_data = load_site(site_id)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return

    # Build a scene dict compatible with visualizer.py
    context_buildings = site_data.get("context_buildings", [])

    # Add mesh_3d to each building (computed on the fly)
    for b in context_buildings:
        mesh = extrude_polygon_to_3d_mesh(b["vertices_2d"], b.get("height", 20.0))
        if mesh:
            b["mesh_3d"] = mesh

    scene = {
        "city_key": f"{site_data['city']}_{site_data['zone']}",
        "city_name": f"{site_data['city'].replace('_', ' ').title()} — {site_data['zone'].replace('_', ' ').title()}",
        "typology": site_data.get("typology", "unknown"),
        "density_class": site_data.get("density_tier", "unknown"),
        "coordinates": site_data.get("coordinates", {}),
        "verification_links": site_data.get("verification_links", {}),
        "radius_m": site_data.get("radius_m", 100.0),
        "site_boundary": site_data.get("site_boundary", {}),
        "context_buildings": context_buildings,
        "roads": site_data.get("roads", []),
        "metrics": site_data.get("metrics", {}),
    }

    # Fill in missing metric keys that visualizer expects
    metrics = scene["metrics"]
    if "site_area_m2" not in metrics:
        # Compute from site boundary
        sb = scene["site_boundary"].get("vertices_2d", [])
        if sb and len(sb) >= 3:
            verts = np.array(sb)
            x, y = verts[:, 0], verts[:, 1]
            metrics["site_area_m2"] = round(
                0.5 * abs(float(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))), 2
            )
        else:
            metrics["site_area_m2"] = 0.0

    if "floor_area_ratio" not in metrics:
        metrics["floor_area_ratio"] = metrics.get("far", 0.0)
    if "building_count" not in metrics:
        metrics["building_count"] = len(context_buildings)
    if "max_height_m" not in metrics:
        metrics["max_height_m"] = metrics.get("max_height", 0.0)

    # Render via visualizer
    try:
        from visualizer import create_3d_context_visualization
    except ImportError:
        print("Error: Could not import visualizer.py")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, f"{site_id}_3d.html")
    create_3d_context_visualization(scene, output_path)

    coords = site_data.get("coordinates", {})
    print(f"\n  Site ID     : {site_id}")
    print(f"  City/Zone   : {site_data['city']} / {site_data['zone']}")
    print(f"  Coordinates : {coords.get('lat', '?')}, {coords.get('lon', '?')}")
    print(f"  FAR         : {metrics.get('far', '?')}")
    print(f"  Buildings   : {metrics.get('building_count', '?')}")
    print(f"  Max Height  : {metrics.get('max_height', '?')}m")
    print(f"  Viewer      : {output_path}")

    # Open in browser
    webbrowser.open(f"file://{os.path.abspath(output_path)}")


def handle_stats(args):
    """Print aggregate database statistics."""
    stats = get_stats()

    if stats["total"] == 0:
        print("Database is empty. Run batch_fetcher.py first.")
        return

    print(f"\n{'=' * 60}")
    print(f"  URBAN CONTEXT DATABASE — STATISTICS")
    print(f"{'=' * 60}")
    print(f"  Total sites : {stats['total']}")
    print()

    print("  By City:")
    for city, count in stats["by_city"].items():
        print(f"    {city:<20s} : {count}")
    print()

    print("  By Density Tier:")
    for tier, count in stats["by_density_tier"].items():
        print(f"    {tier:<20s} : {count}")
    print()

    print("  By Typology:")
    for typ, count in stats["by_typology"].items():
        print(f"    {typ:<20s} : {count}")
    print()

    print(f"  FAR Range       : {stats['far_range'][0]:.1f} – {stats['far_range'][1]:.1f}")
    print(f"  FAR Mean        : {stats['far_mean']:.1f}")
    print(f"  Max Height Range: {stats['max_height_range'][0]:.1f}m – {stats['max_height_range'][1]:.1f}m")
    print(f"  Avg Bldg Count  : {stats['avg_building_count']:.0f}")
    print(f"{'=' * 60}")


def handle_dashboard(args):
    """Generate and open an HTML dashboard for browsing all sites."""
    from site_database import list_sites as db_list_sites

    sites = db_list_sites(sort_by="far", descending=True)
    if not sites:
        print("Database is empty. Run batch_fetcher.py first.")
        return

    stats = get_stats()

    # Build HTML dashboard
    rows_html = ""
    for s in sites:
        gmaps = f"https://www.google.com/maps?q={s['lat']},{s['lon']}"
        rows_html += f"""
        <tr>
            <td><strong>{s['id']}</strong></td>
            <td>{s['city']}</td>
            <td>{s['zone']}</td>
            <td><span class="badge badge-{s['typology'].replace('_', '-')}">{s['typology']}</span></td>
            <td><span class="badge badge-{s['density_tier'].replace('_', '-')}">{s['density_tier']}</span></td>
            <td class="num">{s['far']:.1f}</td>
            <td class="num">{s['gcr']:.3f}</td>
            <td class="num">{s['building_count']}</td>
            <td class="num">{s['max_height']:.1f}m</td>
            <td class="num">{s['avg_height']:.1f}m</td>
            <td><a href="{gmaps}" target="_blank" title="Google Maps">🗺️</a></td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Urban Context Database — Dashboard</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #0f0f13;
            color: #e0e0e6;
            padding: 24px;
        }}
        h1 {{
            font-size: 1.8rem;
            font-weight: 700;
            background: linear-gradient(135deg, #818cf8, #a78bfa, #c084fc);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 8px;
        }}
        .subtitle {{ color: #888; margin-bottom: 24px; font-size: 0.9rem; }}
        .stats-row {{
            display: flex;
            gap: 16px;
            margin-bottom: 28px;
            flex-wrap: wrap;
        }}
        .stat-card {{
            background: #1a1a24;
            border: 1px solid #2a2a3a;
            border-radius: 12px;
            padding: 16px 24px;
            min-width: 140px;
        }}
        .stat-card .label {{ font-size: 0.75rem; color: #888; text-transform: uppercase; letter-spacing: 0.5px; }}
        .stat-card .value {{ font-size: 1.6rem; font-weight: 700; color: #c084fc; margin-top: 4px; }}
        .filter-bar {{
            display: flex;
            gap: 12px;
            margin-bottom: 16px;
            align-items: center;
            flex-wrap: wrap;
        }}
        .filter-bar input, .filter-bar select {{
            background: #1a1a24;
            border: 1px solid #2a2a3a;
            color: #e0e0e6;
            padding: 8px 14px;
            border-radius: 8px;
            font-size: 0.85rem;
            outline: none;
        }}
        .filter-bar input:focus, .filter-bar select:focus {{
            border-color: #818cf8;
        }}
        .filter-bar label {{ font-size: 0.8rem; color: #888; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: #1a1a24;
            border-radius: 12px;
            overflow: hidden;
            border: 1px solid #2a2a3a;
        }}
        th {{
            background: #22223a;
            padding: 12px 14px;
            text-align: left;
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: #999;
            cursor: pointer;
            user-select: none;
            white-space: nowrap;
        }}
        th:hover {{ color: #c084fc; }}
        td {{
            padding: 10px 14px;
            border-top: 1px solid #1f1f2f;
            font-size: 0.85rem;
        }}
        td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
        tr:hover td {{ background: #22223a; }}
        .badge {{
            padding: 3px 10px;
            border-radius: 6px;
            font-size: 0.72rem;
            font-weight: 600;
            text-transform: uppercase;
        }}
        .badge-strict-grid {{ background: #1e3a5f; color: #60a5fa; }}
        .badge-organic {{ background: #3a2a1e; color: #fb923c; }}
        .badge-organic-constrained {{ background: #3a1e2a; color: #f472b6; }}
        .badge-mid {{ background: #1e3a2a; color: #4ade80; }}
        .badge-high {{ background: #3a3a1e; color: #facc15; }}
        .badge-very-high {{ background: #3a1e1e; color: #f87171; }}
        a {{ color: #818cf8; text-decoration: none; }}
        a:hover {{ color: #c084fc; }}
        .count-display {{ color: #888; font-size: 0.85rem; margin-bottom: 8px; }}
    </style>
</head>
<body>
    <h1>Urban Context Database</h1>
    <p class="subtitle">Collected real-world urban contexts from OpenStreetMap for building simulation</p>

    <div class="stats-row">
        <div class="stat-card">
            <div class="label">Total Sites</div>
            <div class="value">{stats['total']}</div>
        </div>
        <div class="stat-card">
            <div class="label">FAR Range</div>
            <div class="value">{stats['far_range'][0]:.1f}–{stats['far_range'][1]:.1f}</div>
        </div>
        <div class="stat-card">
            <div class="label">FAR Mean</div>
            <div class="value">{stats['far_mean']:.1f}</div>
        </div>
        <div class="stat-card">
            <div class="label">Avg Buildings</div>
            <div class="value">{stats['avg_building_count']:.0f}</div>
        </div>
        <div class="stat-card">
            <div class="label">Height Range</div>
            <div class="value">{stats['max_height_range'][0]:.0f}–{stats['max_height_range'][1]:.0f}m</div>
        </div>
    </div>

    <div class="filter-bar">
        <label>Search:</label>
        <input type="text" id="searchInput" placeholder="Filter by city, zone, ID..." oninput="filterTable()">
        <label>Tier:</label>
        <select id="tierFilter" onchange="filterTable()">
            <option value="">All</option>
            <option value="mid">Mid</option>
            <option value="high">High</option>
            <option value="very_high">Very High</option>
        </select>
        <label>Typology:</label>
        <select id="typologyFilter" onchange="filterTable()">
            <option value="">All</option>
            <option value="strict_grid">Strict Grid</option>
            <option value="organic">Organic</option>
        </select>
    </div>

    <p class="count-display" id="countDisplay">Showing {len(sites)} sites</p>

    <table id="sitesTable">
        <thead>
            <tr>
                <th>ID</th>
                <th>City</th>
                <th>Zone</th>
                <th>Typology</th>
                <th>Tier</th>
                <th>FAR</th>
                <th>GCR</th>
                <th>Buildings</th>
                <th>Max Height</th>
                <th>Avg Height</th>
                <th>Map</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>

    <script>
        function filterTable() {{
            const search = document.getElementById('searchInput').value.toLowerCase();
            const tier = document.getElementById('tierFilter').value;
            const typology = document.getElementById('typologyFilter').value;
            const rows = document.querySelectorAll('#sitesTable tbody tr');
            let visible = 0;
            rows.forEach(row => {{
                const text = row.textContent.toLowerCase();
                const matchSearch = !search || text.includes(search);
                const matchTier = !tier || text.includes(tier);
                const matchTypology = !typology || text.includes(typology);
                const show = matchSearch && matchTier && matchTypology;
                row.style.display = show ? '' : 'none';
                if (show) visible++;
            }});
            document.getElementById('countDisplay').textContent = 'Showing ' + visible + ' sites';
        }}

        // Simple column sorting
        document.querySelectorAll('#sitesTable th').forEach((th, idx) => {{
            th.addEventListener('click', () => {{
                const tbody = document.querySelector('#sitesTable tbody');
                const rows = Array.from(tbody.querySelectorAll('tr'));
                const asc = th.dataset.sort !== 'asc';
                th.dataset.sort = asc ? 'asc' : 'desc';
                rows.sort((a, b) => {{
                    let va = a.children[idx].textContent.trim();
                    let vb = b.children[idx].textContent.trim();
                    const na = parseFloat(va.replace('m', ''));
                    const nb = parseFloat(vb.replace('m', ''));
                    if (!isNaN(na) && !isNaN(nb)) {{
                        return asc ? na - nb : nb - na;
                    }}
                    return asc ? va.localeCompare(vb) : vb.localeCompare(va);
                }});
                rows.forEach(r => tbody.appendChild(r));
            }});
        }});
    </script>
</body>
</html>"""

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    dashboard_path = os.path.join(OUTPUT_DIR, "database_dashboard.html")
    with open(dashboard_path, "w") as f:
        f.write(html)

    print(f"Dashboard saved to: {dashboard_path}")
    webbrowser.open(f"file://{os.path.abspath(dashboard_path)}")


def main():
    parser = argparse.ArgumentParser(
        description="Browse and visualize the urban context database"
    )
    subparsers = parser.add_subparsers(dest="command", help="Sub-command")

    # list
    list_parser = subparsers.add_parser("list", help="List all sites")
    list_parser.add_argument("--sort", default="far",
                             help="Sort by field (far, gcr, building_count, max_height, avg_height)")
    list_parser.add_argument("--ascending", action="store_true",
                             help="Sort ascending instead of descending")
    list_parser.add_argument("--city", type=str, help="Filter by city")
    list_parser.add_argument("--tier", type=str, help="Filter by density tier (mid, high, very_high)")
    list_parser.add_argument("--typology", type=str, help="Filter by typology (strict_grid, organic)")

    # view
    view_parser = subparsers.add_parser("view", help="Visualize a specific site in 3D")
    view_parser.add_argument("site_id", type=str, help="Site ID (e.g. site_0001 or just 0001)")

    # stats
    subparsers.add_parser("stats", help="Show aggregate database statistics")

    # dashboard
    subparsers.add_parser("dashboard", help="Open HTML dashboard in browser")

    args = parser.parse_args()

    if args.command == "list":
        handle_list(args)
    elif args.command == "view":
        handle_view(args)
    elif args.command == "stats":
        handle_stats(args)
    elif args.command == "dashboard":
        handle_dashboard(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
