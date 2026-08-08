#!/usr/bin/env python3
"""Apply cached auto-translated-overrides.json to de.json for remaining shells."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "scripts" / "translation-patches" / "de" / "auto-translated-overrides.json"
DE = ROOT / "locales" / "de.json"


def set_leaf(obj: dict, dotted: str, value: str) -> None:
    parts = dotted.split(".")
    node = obj
    for part in parts[:-1]:
        if part not in node or not isinstance(node[part], dict):
            node[part] = {}
        node = node[part]
    node[parts[-1]] = value


def main() -> None:
    cache = json.loads(CACHE.read_text(encoding="utf-8"))
    de = json.loads(DE.read_text(encoding="utf-8"))
    proc = subprocess.run(
        ["node", "scripts/i18n-dump-remaining.mjs", "de", "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    shells = json.loads(proc.stdout)
    applied = 0
    for item in shells:
        en_val = item["en"]
        de_val = cache.get(en_val)
        if not de_val or de_val == en_val:
            continue
        set_leaf(de, item["key"], de_val)
        applied += 1
    DE.write_text(json.dumps(de, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"partial applied={applied}")


if __name__ == "__main__":
    main()
