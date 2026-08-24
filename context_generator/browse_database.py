"""
Browse Database CLI Tool — Inspect saved sites and render 3D WebGL visualizations.
"""

import sys
import argparse
from site_database import list_sites, load_site
from visualizer import create_3d_context_visualization


def main():
    parser = argparse.ArgumentParser(description="Browse urban context database sites")
    subparsers = parser.add_subparsers(dest="command")

    # List command
    list_parser = subparsers.add_parser("list", help="List sites in database")
    list_parser.add_argument("--city", type=str, default=None, help="Filter by city")
    list_parser.add_argument("--limit", type=int, default=50, help="Max results")

    # View command
    view_parser = subparsers.add_parser("view", help="Render 3D HTML viewer for a site")
    view_parser.add_argument("site_id", type=str, help="Site ID (e.g. site_0001 or site_0005)")

    args = parser.parse_args()

    if args.command == "list" or args.command is None:
        city_filter = getattr(args, "city", None)
        limit_val = getattr(args, "limit", 50)
        sites = list_sites(limit=limit_val, city=city_filter)

        print(f"\n{'Site ID':<12} {'City':<15} {'Zone':<15} {'Area (m²)':<10} {'Tier':<6} {'FAR':<6} {'Bldgs':<6} {'Max H (m)':<10}")
        print("-" * 85)
        for row in sites:
            # row: (site_id, city, zone, lat, lon, area, tier, far, gcr, bldgs, max_h, avg_h, density_tier, created_at)
            print(f"{row[0]:<12} {row[1]:<15} {row[2]:<15} {row[5]:<10.1f} {row[6]:<6} {row[7]:<6.2f} {row[9]:<6} {row[10]:<10.1f}")
        print(f"\nTotal sites listed: {len(sites)}")

    elif args.command == "view":
        site_id = args.site_id
        scene_data = load_site(site_id)
        if not scene_data:
            print(f"[Error] Site '{site_id}' not found in database.")
            sys.exit(1)

        out_file = create_3d_context_visualization(scene_data)
        if out_file:
            print(f"\n  Site ID     : {site_id}")
            print(f"  City/Zone   : {scene_data.get('city', '?')} / {scene_data.get('zone', '?')}")
            print(f"  Coordinates : {scene_data['coordinates']['lat']}, {scene_data['coordinates']['lon']}")
            print(f"  FAR         : {scene_data['metrics'].get('far', '?')}")
            print(f"  Buildings   : {len(scene_data.get('context_buildings', []))}")
            print(f"  Max Height  : {scene_data['metrics'].get('max_height', '?')}m")
            print(f"  Viewer      : {out_file}\n")


if __name__ == "__main__":
    main()
