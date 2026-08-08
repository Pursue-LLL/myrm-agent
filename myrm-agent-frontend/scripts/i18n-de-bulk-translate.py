#!/usr/bin/env python3
"""Bulk-translate de.json translation shells from en SSOT via Google Translate (formal de)."""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from deep_translator import GoogleTranslator

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "locales"
GLOSSARY = ROOT / "scripts" / "i18n-glossary.json"
OUT_OVERRIDES = ROOT / "scripts" / "translation-patches" / "de" / "auto-translated-overrides.json"

PLACEHOLDER_RE = re.compile(r"\{[^{}]+\}")
ICU_BLOCK_RE = re.compile(r"\{[^{}]*,[^}]*\}")

BRANDS = [
    "Myrm",
    "MyrmAgent",
    "MCP",
    "OpenAI",
    "GitHub",
    "Telegram",
    "Discord",
    "Slack",
    "Webhook",
    "OAuth2",
    "OAuth",
    "API",
    "URL",
    "JSON",
    "YAML",
    "SSE",
    "ICU",
    "Tauri",
    "Next.js",
    "LangGraph",
]


def protect(text: str) -> tuple[str, list[str]]:
    tokens: list[str] = []

    def repl(m: re.Match[str]) -> str:
        tokens.append(m.group(0))
        return f"__PH{len(tokens) - 1}__"

    protected = PLACEHOLDER_RE.sub(repl, text)
    return protected, tokens


def restore(text: str, tokens: list[str]) -> str:
    out = text
    for i, tok in enumerate(tokens):
        out = out.replace(f"__PH{i}__", tok)
        out = out.replace(f"__PH {i} __", tok)
        out = out.replace(f"__ PH {i} __", tok)
    return out


def protect_brands(text: str) -> str:
    out = text
    for brand in BRANDS:
        out = out.replace(brand, f"__BR_{brand}__")
    return out


def restore_brands(text: str) -> str:
    out = text
    for brand in BRANDS:
        out = out.replace(f"__BR_{brand}__", brand)
        out = out.replace(f"__ BR _{brand}__", brand)
    return out


def set_leaf(obj: dict, dotted: str, value: str) -> None:
    parts = dotted.split(".")
    node = obj
    for part in parts[:-1]:
        if part not in node or not isinstance(node[part], dict):
            node[part] = {}
        node = node[part]
    node[parts[-1]] = value


def collect_shells(en: dict, de: dict, allow: dict) -> list[tuple[str, str]]:
    # mirror i18n-shell-core isLegitSameValue + shell rules (minimal)
    from subprocess import run

    proc = run(
        ["node", "-e", """
import { collectTranslationShells, loadShellAllowlist } from './scripts/i18n-shell-core.mjs';
import fs from 'fs';
const en=JSON.parse(fs.readFileSync('locales/en.json','utf8'));
const de=JSON.parse(fs.readFileSync('locales/de.json','utf8'));
const allow=loadShellAllowlist('.');
console.log(JSON.stringify(collectTranslationShells(en,de,allow)));
"""],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(proc.stdout.strip())
    return [(item["key"], item["en"]) for item in data]


def main() -> None:
    en = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))
    de_path = LOCALES / "de.json"
    de = json.loads(de_path.read_text(encoding="utf-8"))

    shells = collect_shells(en, de, {})
    print(f"shells={len(shells)}")

    unique_en: dict[str, str | None] = {}
    for _key, en_val in shells:
        if en_val not in unique_en:
            unique_en[en_val] = None

    translator = GoogleTranslator(source="en", target="de")
    cache: dict[str, str] = {}
    if OUT_OVERRIDES.exists():
        cache.update(json.loads(OUT_OVERRIDES.read_text(encoding="utf-8")))

    total = len(unique_en)
    done = 0
    for en_val in unique_en:
        if en_val in cache and cache[en_val] != en_val:
            unique_en[en_val] = cache[en_val]
            done += 1
            continue
        if not en_val.strip() or en_val == en_val.upper() and len(en_val) <= 3:
            cache[en_val] = en_val
            unique_en[en_val] = en_val
            done += 1
            continue

        protected, tokens = protect(en_val)
        protected = protect_brands(protected)
        try:
            translated = translator.translate(protected)
        except Exception as exc:  # noqa: BLE001
            print(f"WARN translate failed: {en_val!r} -> {exc}", file=sys.stderr)
            time.sleep(1)
            try:
                translated = translator.translate(protected)
            except Exception as exc2:  # noqa: BLE001
                print(f"SKIP after retry: {en_val!r} -> {exc2}", file=sys.stderr)
                cache[en_val] = en_val
                unique_en[en_val] = en_val
                done += 1
                continue
        translated = restore_brands(translated)
        translated = restore(translated, tokens)
        cache[en_val] = translated
        unique_en[en_val] = translated
        done += 1
        if done % 50 == 0:
            print(f"translated {done}/{total}", flush=True)
            OUT_OVERRIDES.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            time.sleep(0.15)

    OUT_OVERRIDES.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    applied = 0
    for key, en_val in shells:
        de_val = unique_en.get(en_val) or cache.get(en_val)
        if not de_val or de_val == en_val:
            continue
        set_leaf(de, key, de_val)
        applied += 1

    de_path.write_text(json.dumps(de, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"applied={applied} de.json updated")


if __name__ == "__main__":
    main()
