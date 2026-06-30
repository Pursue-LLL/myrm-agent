"""Tests for Obsidian Vault adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.wiki.obsidian_adapter import (
    ObsidianImportStats,
    adapt_obsidian_file,
    parse_frontmatter,
    rewrite_image_embeds,
)


# ---------------------------------------------------------------------------
# parse_frontmatter
# ---------------------------------------------------------------------------


class TestParseFrontmatter:
    def test_inline_array_tags(self) -> None:
        content = "---\ntags: [python, web, ai]\n---\n# Hello\n"
        meta, body = parse_frontmatter(content)
        assert meta["tags"] == ["python", "web", "ai"]
        assert body.startswith("# Hello")

    def test_yaml_indented_list_tags(self) -> None:
        content = "---\ntags:\n  - python\n  - web\n  - ai\n---\n# Hello\n"
        meta, body = parse_frontmatter(content)
        assert meta["tags"] == ["python", "web", "ai"]

    def test_yaml_indented_list_aliases(self) -> None:
        content = "---\naliases:\n  - my-note\n  - test\n---\n# Hello\n"
        meta, body = parse_frontmatter(content)
        assert meta["aliases"] == ["my-note", "test"]

    def test_mixed_inline_and_indented(self) -> None:
        content = "---\ntags: [inline-tag]\naliases:\n  - alias-a\n  - alias-b\ncreated: 2024-01-15\n---\n# Hello\n"
        meta, body = parse_frontmatter(content)
        assert meta["tags"] == ["inline-tag"]
        assert meta["aliases"] == ["alias-a", "alias-b"]
        assert meta["created"] == "2024-01-15"

    def test_no_frontmatter(self) -> None:
        content = "# Hello\nNo frontmatter here\n"
        meta, body = parse_frontmatter(content)
        assert meta == {}
        assert body == content

    def test_empty_list_key_followed_by_new_key(self) -> None:
        content = "---\ntags:\ncreated: 2024-01-15\n---\n# Hello\n"
        meta, _ = parse_frontmatter(content)
        assert "tags" not in meta
        assert meta["created"] == "2024-01-15"

    def test_quoted_values(self) -> None:
        content = '---\ntitle: "My Note"\nauthor: \'John\'\n---\n# Hello\n'
        meta, _ = parse_frontmatter(content)
        assert meta["title"] == "My Note"
        assert meta["author"] == "John"

    def test_keys_lowercased(self) -> None:
        content = "---\nTags: [a, b]\nCreated: 2024\n---\n# Hello\n"
        meta, _ = parse_frontmatter(content)
        assert "tags" in meta
        assert "created" in meta

    def test_empty_content(self) -> None:
        meta, body = parse_frontmatter("")
        assert meta == {}
        assert body == ""

    def test_frontmatter_strips_from_body(self) -> None:
        content = "---\ntitle: test\n---\nBody content here"
        meta, body = parse_frontmatter(content)
        assert meta["title"] == "test"
        assert "---" not in body
        assert "Body content here" in body


# ---------------------------------------------------------------------------
# rewrite_image_embeds
# ---------------------------------------------------------------------------


class TestRewriteImageEmbeds:
    def test_rewrites_existing_image(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        img = vault / "photo.png"
        img.write_bytes(b"\x89PNG")
        md_file = vault / "note.md"
        md_file.write_text("See ![[photo.png]] here")
        assets = tmp_path / "assets"

        result, count = rewrite_image_embeds("See ![[photo.png]] here", md_file, vault, assets)
        assert count == 1
        assert "![photo](photo.png)" in result
        assert (assets / "photo.png").exists()

    def test_preserves_missing_image(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        md_file = vault / "note.md"
        md_file.write_text("See ![[missing.png]] here")

        result, count = rewrite_image_embeds("See ![[missing.png]] here", md_file, vault, tmp_path / "assets")
        assert count == 0
        assert "![[missing.png]]" in result

    def test_no_duplicate_copy(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        img = vault / "photo.png"
        img.write_bytes(b"\x89PNG")
        md_file = vault / "note.md"
        assets = tmp_path / "assets"
        assets.mkdir()
        (assets / "photo.png").write_bytes(b"\x89PNG_OLD")

        _, count = rewrite_image_embeds("![[photo.png]]", md_file, vault, assets)
        assert count == 1
        assert (assets / "photo.png").read_bytes() == b"\x89PNG_OLD"

    def test_case_insensitive_extension(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        img = vault / "photo.JPG"
        img.write_bytes(b"\xff\xd8")
        md_file = vault / "note.md"
        assets = tmp_path / "assets"

        result, count = rewrite_image_embeds("![[photo.JPG]]", md_file, vault, assets)
        assert count == 1


# ---------------------------------------------------------------------------
# adapt_obsidian_file
# ---------------------------------------------------------------------------


class TestAdaptObsidianFile:
    def test_processes_md_with_frontmatter(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        note = vault / "note.md"
        note.write_text("---\ntags:\n  - python\n  - web\n---\n# Hello\nContent here")
        raw = tmp_path / "raw"
        assets = tmp_path / "assets"

        dest, meta, imgs = adapt_obsidian_file(note, vault, raw, assets)
        assert dest is not None
        assert dest.exists()
        text = dest.read_text()
        assert "Tags: python, web" in text
        assert "# Hello" in text
        assert meta["tags"] == ["python", "web"]
        assert imgs == 0

    def test_skips_canvas_file(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        canvas = vault / "board.canvas"
        canvas.write_text("{}")
        raw = tmp_path / "raw"
        assets = tmp_path / "assets"

        dest, meta, imgs = adapt_obsidian_file(canvas, vault, raw, assets)
        assert dest is None
        assert meta == {}

    def test_handles_unicode_error(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        binary = vault / "broken.md"
        binary.write_bytes(b"\x80\x81\x82\x83" * 100)
        raw = tmp_path / "raw"
        assets = tmp_path / "assets"

        dest, meta, imgs = adapt_obsidian_file(binary, vault, raw, assets)
        assert dest is not None or dest is None  # Should not raise

    def test_preserves_directory_structure(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        (vault / "sub" / "deep").mkdir(parents=True)
        note = vault / "sub" / "deep" / "note.md"
        note.write_text("# Nested note")
        raw = tmp_path / "raw"
        assets = tmp_path / "assets"

        dest, _, _ = adapt_obsidian_file(note, vault, raw, assets)
        assert dest is not None
        assert "sub/deep/note.md" in str(dest)

    def test_aliases_prepended(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        note = vault / "note.md"
        note.write_text("---\naliases:\n  - alias1\n  - alias2\n---\n# Test")
        raw = tmp_path / "raw"
        assets = tmp_path / "assets"

        dest, meta, _ = adapt_obsidian_file(note, vault, raw, assets)
        assert dest is not None
        text = dest.read_text()
        assert "Aliases: alias1, alias2" in text


# ---------------------------------------------------------------------------
# ObsidianImportStats
# ---------------------------------------------------------------------------


class TestObsidianImportStats:
    def test_default_values(self) -> None:
        stats = ObsidianImportStats()
        assert stats.files_scanned == 0
        assert stats.files_processed == 0
        assert stats.errors == []

    def test_mutable_errors_list(self) -> None:
        s1 = ObsidianImportStats()
        s2 = ObsidianImportStats()
        s1.errors.append("err")
        assert s2.errors == []


# ---------------------------------------------------------------------------
# Edge cases & full pipeline
# ---------------------------------------------------------------------------


class TestParseFrontmatterEdgeCases:
    def test_comment_lines_in_frontmatter(self) -> None:
        content = "---\n# comment line\ntags: [a]\n---\nBody"
        meta, body = parse_frontmatter(content)
        assert meta["tags"] == ["a"]
        assert "Body" in body

    def test_colon_in_value(self) -> None:
        content = "---\ntitle: My Title: Extended\n---\nBody"
        meta, _ = parse_frontmatter(content)
        assert meta["title"] == "My Title: Extended"

    def test_list_with_quoted_items(self) -> None:
        content = "---\ntags:\n  - 'quoted-tag'\n  - \"double-quoted\"\n---\nBody"
        meta, _ = parse_frontmatter(content)
        assert meta["tags"] == ["quoted-tag", "double-quoted"]

    def test_multiple_lists_sequential(self) -> None:
        content = "---\ntags:\n  - a\n  - b\naliases:\n  - x\n  - y\ncreated: 2024\n---\nBody"
        meta, _ = parse_frontmatter(content)
        assert meta["tags"] == ["a", "b"]
        assert meta["aliases"] == ["x", "y"]
        assert meta["created"] == "2024"

    def test_single_item_list(self) -> None:
        content = "---\ntags:\n  - solo\n---\nBody"
        meta, _ = parse_frontmatter(content)
        assert meta["tags"] == ["solo"]

    def test_frontmatter_only_no_body(self) -> None:
        content = "---\ntitle: test\n---\n"
        meta, body = parse_frontmatter(content)
        assert meta["title"] == "test"
        assert body == ""


class TestRewriteImageEdgeCases:
    def test_multiple_images_in_one_line(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "a.png").write_bytes(b"\x89PNG")
        (vault / "b.jpg").write_bytes(b"\xff\xd8")
        md_file = vault / "note.md"
        assets = tmp_path / "assets"

        result, count = rewrite_image_embeds("![[a.png]] and ![[b.jpg]]", md_file, vault, assets)
        assert count == 2
        assert "![a](a.png)" in result
        assert "![b](b.jpg)" in result

    def test_image_in_subdirectory(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        (vault / "attachments").mkdir(parents=True)
        (vault / "attachments" / "img.png").write_bytes(b"\x89PNG")
        md_file = vault / "note.md"
        md_file.write_text("")
        assets = tmp_path / "assets"

        result, count = rewrite_image_embeds("![[attachments/img.png]]", md_file, vault, assets)
        assert count == 1

    def test_non_image_embed_ignored(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        md_file = vault / "note.md"
        assets = tmp_path / "assets"

        result, count = rewrite_image_embeds("![[some-note]]", md_file, vault, assets)
        assert count == 0
        assert "![[some-note]]" in result


class TestAdaptFullPipeline:
    def test_full_vault_simulation(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        (vault / "daily").mkdir(parents=True)
        (vault / "attachments").mkdir()

        (vault / "note1.md").write_text(
            "---\ntags:\n  - python\n  - web\naliases:\n  - n1\ncreated: 2024-01-01\n---\n# Note 1\nContent"
        )
        (vault / "daily" / "2024-01-01.md").write_text("# Daily\nNo frontmatter")
        (vault / "attachments" / "img.png").write_bytes(b"\x89PNG")
        (vault / "note_with_img.md").write_text(
            "---\ntags: [photo]\n---\nSee ![[img.png]] here"
        )
        (vault / "skip.canvas").write_text("{}")

        raw = tmp_path / "raw"
        assets = tmp_path / "assets"

        stats = ObsidianImportStats()
        for md_file in vault.rglob("*.md"):
            stats.files_scanned += 1
            dest, meta, imgs = adapt_obsidian_file(md_file, vault, raw, assets)
            if dest:
                stats.files_processed += 1
                if isinstance(meta.get("tags"), list):
                    stats.tags_extracted += len(meta["tags"])
                stats.images_copied += imgs

        assert stats.files_scanned == 3
        assert stats.files_processed == 3
        assert stats.tags_extracted == 3
        assert stats.images_copied == 1

        note1 = raw / "note1.md"
        assert note1.exists()
        text = note1.read_text()
        assert "Tags: python, web" in text
        assert "Aliases: n1" in text

    def test_empty_vault(self, tmp_path: Path) -> None:
        vault = tmp_path / "empty_vault"
        vault.mkdir()
        raw = tmp_path / "raw"
        assets = tmp_path / "assets"

        md_files = list(vault.rglob("*.md"))
        assert len(md_files) == 0

    def test_binary_file_resilience(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "binary.md").write_bytes(bytes(range(256)) * 10)
        raw = tmp_path / "raw"
        assets = tmp_path / "assets"

        dest, meta, imgs = adapt_obsidian_file(vault / "binary.md", vault, raw, assets)
        assert imgs == 0
