import requests, json

query = """[out:json][timeout:25];(way["building"](around:150,40.7580,-73.9855);way["highway"](around:150,40.7580,-73.9855););out body geom;"""

endpoints = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass-api.de/api/interpreter"
]

for ep in endpoints:
    try:
        resp = requests.post(ep, data={'data': query}, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=15)
        print(ep, "-> STATUS CODE:", resp.status_code)
        if resp.status_code == 200:
            data = resp.json()
            elements = data.get("elements", [])
            print(f"SUCCESS on {ep}! Retrieved {len(elements)} raw elements!")
            with open("dataset/raw_osm_overpass_result.json", "w") as f:
                json.dump(data, f, indent=2)
            print("Saved raw Overpass API response to dataset/raw_osm_overpass_result.json!")
            break
    except Exception as e:
        print(ep, "-> FAILED:", e)
