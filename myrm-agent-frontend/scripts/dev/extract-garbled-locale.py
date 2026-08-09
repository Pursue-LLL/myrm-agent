#!/usr/bin/env python3
"""Extract garbled locale entries with en baseline for translation.

Garbled heuristics:
  - contains CJK full-width comma 。;：;【】 etc (Chinese punctuation in ja/ko/de)
  - ja: CJK Han mixed with Chinese-only words/particles
"""
import json
import re
import sys

ROOT = "locales"

def walk(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, f"{path}.{k}" if path else k)
    else:
        yield path, obj

# Chinese punctuation (ja/ko/de use 。、＃etc; comma must be ，in zh only)
CN_PUNCT = re.compile(r"[，。；：【】]")
# Chinese-only particles/words that should never appear in ja/ko/de
CN_WORDS = re.compile(r"[您根据报错框移除调整更新规意见检测构建部署迁移监控资源数据文件支持使用进行以及对于可以不或]")
HAN = re.compile(r"[\u4e00-\u9fff]")

def is_garbled(lang, value):
    if not isinstance(value, str):
        return False
    if CN_PUNCT.search(value):
        return True
    if lang == "ja" and HAN.search(value) and re.search(r"[\u3040-\u30ff]", value):
        return True
    if lang != "zh" and lang != "zh-TW" and HAN.search(value) and not re.search(r"[\u3040-\u30ff]", value):
        # han chars in ko/de/ja with no kana -> likely Chinese residue
        return True
    return False

def main():
    lang = sys.argv[1]
    data = json.load(open(f"{ROOT}/{lang}.json"))
    en = json.load(open(f"{ROOT}/en.json"))
    garbled = []
    for path, value in walk(data):
        if is_garbled(lang, value):
            # resolve en baseline
            en_value = en
            for seg in path.split("."):
                if isinstance(en_value, dict) and seg in en_value:
                    en_value = en_value[seg]
                else:
                    en_value = None
                    break
            garbled.append((path, value, en_value))
    out = f"/tmp/garbled_{lang}.jsonl"
    with open(out, "w") as f:
        for path, value, en_value in garbled:
            f.write(json.dumps({"path": path, "current": value, "en": en_value}, ensure_ascii=False) + "\n")
    print(f"{lang}: {len(garbled)} garbled entries -> {out}")

if __name__ == "__main__":
    main()
