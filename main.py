"""
Main CLI Entrypoint for Context Generator.

Commands:
  1. Extract OSM city context (using real 3D OSMnx extractor):
     python main.py extract --city nyc_midtown
     python main.py extract --city tokyo_shinjuku

  2. Generate procedural synthetic context:
     python main.py generate --density high_density --typology strict_grid
     python main.py generate --density superhigh_density --typology organic

  3. List available city presets:
     python main.py list-cities
"""

import argparse
import sys
import os

from config import TARGET_CITIES, DENSITY_PROFILES, OUTPUT_DIR
from extract_real_3d_osmnx import extract_city_osmnx_3d
from procedural_generator import ProceduralContextGenerator
from visualizer import create_3d_context_visualization
from exporter import export_context_to_obj, export_context_to_json


def handle_extract(args):
    print("=" * 65)
    print("      CONTEXT GENERATOR - OSM REAL-WORLD URBAN EXTRACTION")
    print("=" * 65)

    cities_to_extract = []
    if args.all:
        cities_to_extract = list(TARGET_CITIES.keys())
    elif args.city:
        if args.city not in TARGET_CITIES:
            print(f"[Error] Unknown city '{args.city}'. Available presets: {list(TARGET_CITIES.keys())}")
            return
        cities_to_extract = [args.city]
    else:
        cities_to_extract = ["nyc_midtown", "tokyo_shinjuku"]

    for c_key in cities_to_extract:
        extract_city_osmnx_3d(c_key, radius_m=args.radius)

    print("\n[Done] OSM extraction and 3D export complete!")


def handle_generate(args):
    print("=" * 65)
    print("      CONTEXT GENERATOR - PROCEDURAL SYNTHETIC CONTEXT")
    print("=" * 65)

    gen = ProceduralContextGenerator(seed=args.seed)
    scene = gen.generate_context_scene(
        density_class=args.density,
        typology=args.typology,
        radius=args.radius,
        seed=args.seed
    )

    out_name = f"synthetic_{args.density}_{args.typology}"
    print(f"[Procedural Gen] Generated synthetic context ({args.density}, {args.typology})...")
    print(f"  - Site Area: {scene['metrics']['site_area_m2']} m²")
    print(f"  - Context Buildings: {scene['metrics']['building_count']}")
    print(f"  - Floor Area Ratio (FAR): {scene['metrics']['floor_area_ratio']}")
    print(f"  - Sky View Factor (SVF): {scene['metrics']['sky_view_factor']}")

    html_out = os.path.join(OUTPUT_DIR, f"{out_name}_3d.html")
    obj_out = os.path.join(OUTPUT_DIR, f"{out_name}_3d.obj")
    json_out = os.path.join(OUTPUT_DIR, f"{out_name}_context.json")

    create_3d_context_visualization(scene, html_out)
    export_context_to_obj(scene, obj_out)
    export_context_to_json(scene, json_out)

    print(f"\n[Done] Procedural context generated successfully!")


def handle_list_cities(args):
    print("\nTarget City Presets for OSM Context Extraction:")
    print("-" * 65)
    print(f"{'Preset Key':<22} | {'City Name':<30} | {'Typology':<15}")
    print("-" * 65)
    for key, info in TARGET_CITIES.items():
        print(f"{key:<22} | {info['name']:<30} | {info['typology']:<15}")
    print("-" * 65)


def main():
    parser = argparse.ArgumentParser(description="Context Generator for Urban Solar & Environmental Building Simulations")
    subparsers = parser.add_subparsers(dest="command", help="Sub-command to execute")

    extract_parser = subparsers.add_parser("extract", help="Extract real urban contexts from OpenStreetMap")
    extract_parser.add_argument("--city", type=str, help="City key (e.g. nyc_midtown, barcelona_eixample, tokyo_shinjuku)")
    extract_parser.add_argument("--all", action="store_true", help="Extract all city presets")
    extract_parser.add_argument("--radius", type=float, default=160.0, help="Context radius in meters (default 160.0)")

    gen_parser = subparsers.add_parser("generate", help="Synthesize procedural urban context")
    gen_parser.add_argument("--density", type=str, default="high_density", choices=list(DENSITY_PROFILES.keys()), help="Density profile")
    gen_parser.add_argument("--typology", type=str, default="strict_grid", choices=["strict_grid", "organic", "superhigh_tower"], help="Urban grid typology")
    gen_parser.add_argument("--radius", type=float, default=160.0, help="Context radius in meters (default 160.0)")
    gen_parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")

    subparsers.add_parser("list-cities", help="List available city presets")

    args = parser.parse_args()

    if args.command == "extract":
        handle_extract(args)
    elif args.command == "generate":
        handle_generate(args)
    elif args.command == "list-cities":
        handle_list_cities(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
