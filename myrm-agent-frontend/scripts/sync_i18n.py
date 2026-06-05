import json
import os
import copy

def sync_dict(source, target):
    """Recursively sync keys from source to target."""
    changed = False
    for k, v in source.items():
        if k not in target:
            target[k] = copy.deepcopy(v)
            changed = True
        elif isinstance(v, dict) and isinstance(target[k], dict):
            if sync_dict(v, target[k]):
                changed = True
    return changed

def main():
    locales_dir = "/Users/yululiu/projects/AI/open-perplexity/myrm-agent/myrm-agent-frontend/locales"
    zh_path = os.path.join(locales_dir, "zh.json")
    en_path = os.path.join(locales_dir, "en.json")
    ja_path = os.path.join(locales_dir, "ja.json")
    ko_path = os.path.join(locales_dir, "ko.json")
    de_path = os.path.join(locales_dir, "de.json")

    with open(zh_path, 'r', encoding='utf-8') as f:
        zh_data = json.load(f)
    with open(en_path, 'r', encoding='utf-8') as f:
        en_data = json.load(f)
        
    with open(ja_path, 'r', encoding='utf-8') as f:
        ja_data = json.load(f)
    with open(ko_path, 'r', encoding='utf-8') as f:
        ko_data = json.load(f)
    with open(de_path, 'r', encoding='utf-8') as f:
        de_data = json.load(f)

    # Sync en to zh
    sync_dict(en_data, zh_data)
    # Sync zh to en
    sync_dict(zh_data, en_data)
    
    # Sync to other languages just in case they are missing keys too
    sync_dict(en_data, ja_data)
    sync_dict(en_data, ko_data)
    sync_dict(en_data, de_data)

    with open(zh_path, 'w', encoding='utf-8') as f:
        json.dump(zh_data, f, ensure_ascii=False, indent=2)
    with open(en_path, 'w', encoding='utf-8') as f:
        json.dump(en_data, f, ensure_ascii=False, indent=2)
    with open(ja_path, 'w', encoding='utf-8') as f:
        json.dump(ja_data, f, ensure_ascii=False, indent=2)
    with open(ko_path, 'w', encoding='utf-8') as f:
        json.dump(ko_data, f, ensure_ascii=False, indent=2)
    with open(de_path, 'w', encoding='utf-8') as f:
        json.dump(de_data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
