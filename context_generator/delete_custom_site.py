import os
import json
import argparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
CUSTOM_DS_PATH = os.path.join(PROJECT_ROOT, "frontend", "public", "data", "custom_sites_dataset.json")
DIST_CUSTOM_DS_PATH = os.path.join(PROJECT_ROOT, "frontend", "dist", "data", "custom_sites_dataset.json")
SITES_DIR = os.path.join(PROJECT_ROOT, "frontend", "public", "sites")
DIST_SITES_DIR = os.path.join(PROJECT_ROOT, "frontend", "dist", "sites")

def delete_custom_site(site_id: str):
    if not site_id:
        return {"success": False, "error": "No site_id provided"}

    deleted_record = False
    for ds_path in [CUSTOM_DS_PATH, DIST_CUSTOM_DS_PATH]:
        if os.path.exists(ds_path):
            try:
                with open(ds_path, 'r', encoding='utf-8') as f:
                    dataset = json.load(f)
                new_dataset = [item for item in dataset if item.get('site_id') != site_id]
                if len(new_dataset) != len(dataset):
                    deleted_record = True
                with open(ds_path, 'w', encoding='utf-8') as f:
                    json.dump(new_dataset, f, indent=2, ensure_ascii=False)
            except Exception as err:
                pass

    # Delete HTML render files
    for s_dir in [SITES_DIR, DIST_SITES_DIR]:
        html_path = os.path.join(s_dir, f"{site_id}.html")
        if os.path.exists(html_path):
            try:
                os.remove(html_path)
            except Exception:
                pass

    return {"success": True, "site_id": site_id, "deleted": deleted_record}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--site_id', type=str, required=True)
    args = parser.parse_args()
    res = delete_custom_site(args.site_id)
    print(json.dumps(res))
