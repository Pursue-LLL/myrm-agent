"""Seed Instinct Inbox E2E mock drafts via running backend (avoids SQLite lock)."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

_AGENT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_API_BASE = os.getenv("MYRM_API_BASE", "http://127.0.0.1:8080")
SEED_PATH = "/api/v1/skills/drafts/test/seed-mock"


def seed_via_http(api_base: str = DEFAULT_API_BASE) -> dict[str, object]:
    url = f"{api_base.rstrip('/')}{SEED_PATH}"
    req = urllib.request.Request(url, method="POST", data=b"")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


async def seed_direct() -> None:
    server_root = _AGENT_ROOT / "myrm-agent-server"
    sys.path.insert(0, str(server_root))
    from app.api.skills.drafts import seed_mock_drafts_for_e2e
    from app.database.connection import init_database

    await init_database()
    result = await seed_mock_drafts_for_e2e()
    print(f"Created mock drafts: {result['skill_names']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Instinct Inbox E2E mock drafts")
    parser.add_argument(
        "--direct",
        action="store_true",
        help="Write DB directly (only when backend is stopped)",
    )
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help="Backend base URL")
    args = parser.parse_args()

    if args.direct:
        asyncio.run(seed_direct())
        return

    try:
        result = seed_via_http(args.api_base)
        print(f"Seeded mock drafts via API: {result}")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            print(
                "Seed endpoint not found (404). Restart backend after upgrade, or use --direct.",
                file=sys.stderr,
            )
        raise SystemExit(1) from exc
    except urllib.error.URLError as exc:
        print(
            f"Backend not reachable at {args.api_base}. Start ./myrm dev first.",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
