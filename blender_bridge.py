"""
Blender Bridge Script for Context Generator (Hybrid Option C).
Imports generated JSON / OBJ urban context scenes into Blender,
assigning materials, sun light parameters, and camera positioning automatically.

Usage inside Blender or Headless CLI:
  blender --python blender_bridge.py -- dataset/nyc_midtown_context.json
"""

import sys
import os
import json

def run_blender_import(json_path):
    try:
        import bpy
    except ImportError:
        print("[Blender Bridge Error] This script must be executed inside Blender or with Blender's python binary!")
        print("Command example: blender --background --python blender_bridge.py -- <path_to_json>")
        return

    if not os.path.exists(json_path):
        print(f"[Blender Bridge Error] Scene JSON file not found: {json_path}")
        return

    with open(json_path, "r") as f:
        scene_data = json.load(f)

    bpy.ops.wm.read_factory_settings(use_empty=True)

    city_name = scene_data.get("city_name", "Urban Context")
    print(f"[Blender Bridge] Importing scene '{city_name}' into Blender...")

    site_mat = bpy.data.materials.new(name="TestingSite_Material")
    site_mat.use_nodes = True
    site_bsdf = site_mat.node_tree.nodes.get("Principled BSDF")
    if site_bsdf:
        site_bsdf.inputs['Base Color'].default_value = (1.0, 0.7, 0.0, 1.0)

    bldg_mat = bpy.data.materials.new(name="ContextBuilding_Material")
    bldg_mat.use_nodes = True
    bldg_bsdf = bldg_mat.node_tree.nodes.get("Principled BSDF")
    if bldg_bsdf:
        bldg_bsdf.inputs['Base Color'].default_value = (0.7, 0.75, 0.8, 1.0)

    site_verts_2d = scene_data["site_boundary"]["vertices_2d"]
    site_verts_3d = [(v[0], v[1], 0.0) for v in site_verts_2d]
    site_faces = [list(range(len(site_verts_3d)))]

    mesh_site = bpy.data.meshes.new("TestingSite_Mesh")
    mesh_site.from_pydata(site_verts_3d, [], site_faces)
    mesh_site.update()

    obj_site = bpy.data.objects.new("TestingSite", mesh_site)
    bpy.context.collection.objects.link(obj_site)
    obj_site.data.materials.append(site_mat)

    buildings_coll = bpy.data.collections.new("ContextBuildings")
    bpy.context.scene.collection.children.link(buildings_coll)

    for idx, b in enumerate(scene_data["context_buildings"]):
        verts_2d = b["vertices_2d"]
        h = b.get("height", 20.0)
        n = len(verts_2d)

        verts_3d = [(v[0], v[1], 0.0) for v in verts_2d] + [(v[0], v[1], h) for v in verts_2d]
        faces = []

        for i in range(n):
            next_i = (i + 1) % n
            faces.append([i, next_i, next_i + n, i + n])

        faces.append([i + n for i in range(n)])

        mesh_b = bpy.data.meshes.new(f"BldgMesh_{idx}")
        mesh_b.from_pydata(verts_3d, [], faces)
        mesh_b.update()

        obj_b = bpy.data.objects.new(f"Building_{b.get('id', idx)}", mesh_b)
        buildings_coll.objects.link(obj_b)
        obj_b.data.materials.append(bldg_mat)

    sun_data = bpy.data.lights.new(name="SunLight", type='SUN')
    sun_data.energy = 4.5
    sun_obj = bpy.data.objects.new(name="SunLight", object_data=sun_data)
    bpy.context.collection.objects.link(sun_obj)
    sun_obj.location = (50, -100, 120)
    sun_obj.rotation_euler = (0.8, 0.2, 0.5)

    print(f"[Blender Bridge Success] Imported {len(scene_data['context_buildings'])} buildings into Blender scene!")


if __name__ == "__main__":
    args = sys.argv
    if "--" in args:
        idx = args.index("--")
        if idx + 1 < len(args):
            json_file = args[idx + 1]
            run_blender_import(json_file)
        else:
            print("Please provide scene JSON filepath after --")
    else:
        print("Usage: blender --background --python blender_bridge.py -- <path_to_json>")
