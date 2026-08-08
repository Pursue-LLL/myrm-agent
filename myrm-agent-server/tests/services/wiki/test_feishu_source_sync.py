"""Tests for Feishu doc block → markdown conversion."""

from __future__ import annotations

from app.services.wiki.source_sync.feishu import feishu_docx_blocks_to_markdown


def test_feishu_docx_blocks_to_markdown_text_and_heading() -> None:
    payload = {
        "code": 0,
        "data": {
            "items": [
                {
                    "block_type": 3,
                    "heading1": {
                        "elements": [{"text_run": {"content": "Title"}}],
                    },
                },
                {
                    "block_type": 2,
                    "text": {
                        "elements": [{"text_run": {"content": "Body paragraph"}}],
                    },
                },
                {
                    "block_type": 12,
                    "bullet": {
                        "elements": [{"text_run": {"content": "Bullet item"}}],
                    },
                },
            ]
        },
    }
    text = feishu_docx_blocks_to_markdown(payload)
    assert text is not None
    assert "# Title" in text
    assert "Body paragraph" in text
    assert "- Bullet item" in text
