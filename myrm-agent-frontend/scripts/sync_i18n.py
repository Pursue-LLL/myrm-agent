"""本地维护脚本：将 en.json（唯一 SSOT）中缺失的键深拷贝补齐到其余 locale 文件。

只单向同步 en → locale，不反向写回 en；占位符与原文保持一致，译文留给译者。
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

# 与 src/i18n/config.ts locales 保持一致
SUPPORTED_LOCALES: tuple[str, ...] = ("en", "zh", "ja", "ko", "de", "zh-TW")


import re


def extract_placeholders(text: str) -> set[str]:
    return set(re.findall(r"\{([a-zA-Z0-9_]+)\}", text))


def sync_dict(source: dict[str, object], target: dict[str, object]) -> bool:
    """递归将 source 中 target 缺失的键深拷贝到 target，清理孤儿键，并修正不匹配的占位符。"""
    changed = False

    # 1. 删除 target 中存在但在 source 中不存在的孤儿键
    orphan_keys = [k for k in target if k not in source]
    for k in orphan_keys:
        del target[k]
        changed = True

    # 2. 同步与校验
    for key, value in source.items():
        if key not in target:
            target[key] = copy.deepcopy(value)
            changed = True
        elif isinstance(value, dict) and isinstance(target[key], dict):
            if sync_dict(value, target[key]):
                changed = True
        elif isinstance(value, str) and isinstance(target[key], str):
            src_ph = extract_placeholders(value)
            tgt_ph = extract_placeholders(target[key])
            if src_ph != tgt_ph:
                target[key] = value
                changed = True
        elif type(value) is not type(target[key]):
            target[key] = copy.deepcopy(value)
            changed = True

    return changed


def main() -> None:
    locales_dir = Path(__file__).resolve().parents[1] / "locales"
    en_path = locales_dir / "en.json"
    with open(en_path, encoding="utf-8") as fh:
        en_data = json.load(fh)

    for lang in SUPPORTED_LOCALES:
        if lang == "en":
            continue
        path = locales_dir / f"{lang}.json"
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if sync_dict(en_data, data):
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            print(f"synced en -> {lang}")
        else:
            print(f"{lang} already in sync")


if __name__ == "__main__":
    main()
