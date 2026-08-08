"""Tests for Feishu image asset localization (download → wiki/assets rewrite)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from myrm_agent_harness.toolkits.wiki import WikiStructure

from app.services.wiki.source_sync.feishu import _localize_feishu_images


async def _fake_client(images: dict[str, bytes | None]) -> Any:
    class _FakeClient:
        async def download_media(self, token: str) -> bytes | None:
            return images.get(token)

    return _FakeClient()


@pytest.mark.asyncio
async def test_localize_images_success_and_failure_degrade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from myrm_agent_harness.toolkits.wiki.pipeline.ingress import asset_store

    png = b"\x89PNG\r\n\x1a\nfake"
    monkeypatch.setattr(
        asset_store,
        "store_asset_bytes",
        lambda structure, *, data, content_type: "abc123.png" if data == png else None,
    )
    structure = WikiStructure(tmp_path)
    markdown = "![image](feishu-image:tok_ok) and ![image](feishu-image:tok_fail)"
    client = await _fake_client({"tok_ok": png, "tok_fail": None})

    rewritten = await _localize_feishu_images(
        markdown, client, structure=structure, raw_relative="feishu/2026-08/x.md"
    )
    assert "abc123.png" in rewritten
    assert "![image]" in rewritten
    assert "feishu-image:" not in rewritten
