import os
import json
import argparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CUSTOM_DS_PATH = os.path.join(BASE_DIR, "app", "public", "data", "custom_sites_dataset.json")
SITES_DIR = os.path.join(BASE_DIR, "app", "public", "sites")

def delete_custom_site(site_id: str):
    if not site_id:
        return {"success": False, "error": "No site_id provided"}

    deleted_record = False
    if os.path.exists(CUSTOM_DS_PATH):
        try:
            with open(CUSTOM_DS_PATH, 'r', encoding='utf-8') as f:
                dataset = json.load(f)
            new_dataset = []
            for item in dataset:
                if item.get('site_id') == site_id:
                    deleted_record = True
                else:
                    new_dataset.append(item)

            with open(CUSTOM_DS_PATH, 'w', encoding='utf-8') as f:
                json.dump(new_dataset, f, indent=2, ensure_ascii=False)
        except Exception as err:
            return {"success": False, "error": str(err)}

    # Delete HTML render file if present
    html_path = os.path.join(SITES_DIR, f"{site_id}.html")
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
