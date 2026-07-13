"""Warm tab pool — persist hydrated E2E Chrome tabs for parallel MCP reuse.

[INPUT]
- frontend-warmth.json (POS: client_hot generation + warm_tab_pool entries)
- CDP GET /json/list (POS: tab existence refresh)

[OUTPUT]
- merge_warm_tab() / read_warm_tab_pool() / refresh_warm_tab_pool() / pool_for_health_json()

[POS]
Dev infrastructure. Eliminates per-test 30s cold Turbopack compile by reusing warm :3000 tabs.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

MAX_WARM_TAB_POOL = 3
_HOME_URL_SUFFIX = "127.0.0.1:3000/"


class WarmTabEntry(TypedDict):
    targetId: str
    url: str
    title: str
    warmedAt: str


def _state_dir() -> Path:
    override = os.getenv("MYRM_DEV_STATE_DIR", "").strip()
    if override:
        return Path(override)
    return Path.home() / ".local/state/myrm-dev"


def warmth_state_file() -> Path:
    return _state_dir() / "frontend-warmth.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_warmth(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_warmth(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _is_home_tab(url: str) -> bool:
    normalized = url.rstrip("/") + "/"
    return _HOME_URL_SUFFIX in normalized and "/settings" not in normalized


def read_warm_tab_pool(state_file: Path | None = None) -> list[WarmTabEntry]:
    path = state_file or warmth_state_file()
    payload = _load_warmth(path)
    pool = payload.get("warm_tab_pool")
    if not isinstance(pool, list):
        return []
    entries: list[WarmTabEntry] = []
    for item in pool:
        if not isinstance(item, dict):
            continue
        target_id = item.get("targetId")
        url = item.get("url")
        if not isinstance(target_id, str) or not target_id:
            continue
        if not isinstance(url, str) or not url:
            continue
        title = item.get("title")
        warmed_at = item.get("warmedAt")
        entries.append(
            {
                "targetId": target_id,
                "url": url,
                "title": str(title) if isinstance(title, str) else "",
                "warmedAt": str(warmed_at) if isinstance(warmed_at, str) else "",
            }
        )
    return entries


def merge_warm_tab(
    *,
    target_id: str,
    url: str,
    title: str = "",
    state_file: Path | None = None,
) -> list[WarmTabEntry]:
    path = state_file or warmth_state_file()
    payload = _load_warmth(path)
    pool = read_warm_tab_pool(path)
    entry: WarmTabEntry = {
        "targetId": target_id,
        "url": url,
        "title": title,
        "warmedAt": _utc_now_iso(),
    }
    deduped = [item for item in pool if item["targetId"] != target_id]
    deduped.insert(0, entry)
    payload["warm_tab_pool"] = deduped[:MAX_WARM_TAB_POOL]
    _save_warmth(path, payload)
    return read_warm_tab_pool(path)


def _fetch_cdp_pages(cdp_port: int) -> list[dict[str, object]]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{cdp_port}/json/list", timeout=5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def refresh_warm_tab_pool(*, cdp_port: int = 9333, state_file: Path | None = None) -> list[WarmTabEntry]:
    path = state_file or warmth_state_file()
    payload = _load_warmth(path)
    pages = _fetch_cdp_pages(cdp_port)
    live_ids = {
        str(item.get("id"))
        for item in pages
        if isinstance(item.get("id"), str) and item.get("type") == "page"
    }

    kept: list[WarmTabEntry] = []
    for entry in read_warm_tab_pool(path):
        if entry["targetId"] in live_ids:
            kept.append(entry)

    for item in pages:
        if len(kept) >= MAX_WARM_TAB_POOL:
            break
        if item.get("type") != "page":
            continue
        target_id = item.get("id")
        url = item.get("url")
        if not isinstance(target_id, str) or not isinstance(url, str):
            continue
        if not _is_home_tab(url):
            continue
        if any(existing["targetId"] == target_id for existing in kept):
            continue
        title = item.get("title")
        kept.append(
            {
                "targetId": target_id,
                "url": url,
                "title": str(title) if isinstance(title, str) else "",
                "warmedAt": _utc_now_iso(),
            }
        )

    payload["warm_tab_pool"] = kept[:MAX_WARM_TAB_POOL]
    _save_warmth(path, payload)
    return read_warm_tab_pool(path)


def pool_for_health_json(state_file: Path | None = None) -> list[WarmTabEntry]:
    return read_warm_tab_pool(state_file)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Warm tab pool maintenance.")
    parser.add_argument("--refresh", action="store_true", help="Sync pool with live CDP tabs")
    parser.add_argument("--cdp-port", type=int, default=9333)
    parser.add_argument("--state-file", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    state = Path(args.state_file) if args.state_file else None
    if args.refresh:
        pool = refresh_warm_tab_pool(cdp_port=args.cdp_port, state_file=state)
    else:
        pool = read_warm_tab_pool(state)
    if args.json:
        print(json.dumps(pool, separators=(",", ":")))
    else:
        for item in pool:
            print(f"{item['targetId']}\t{item['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
