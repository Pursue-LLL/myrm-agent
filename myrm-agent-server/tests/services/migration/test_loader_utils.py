"""Unit tests for _loader_utils shared utilities."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.migration._loader_utils import (
    extract_env_key_names,
    find_file,
    load_skill_directories,
    markdown_bullets_to_memory,
    path_by_kind,
    read_json,
    read_text,
    read_yaml,
)


class TestReadText:
    def test_reads_utf8_file(self, tmp_path: Path) -> None:
        f = tmp_path / "hello.txt"
        f.write_text("hello world", encoding="utf-8")
        assert read_text(f) == "hello world"

    def test_returns_empty_on_missing_file(self, tmp_path: Path) -> None:
        assert read_text(tmp_path / "nonexistent.txt") == ""

    def test_handles_binary_garbage_gracefully(self, tmp_path: Path) -> None:
        f = tmp_path / "garbage.txt"
        f.write_bytes(b"\xff\xfe\x00\x01 hello")
        result = read_text(f)
        assert "hello" in result


class TestReadJson:
    def test_parses_valid_json(self, tmp_path: Path) -> None:
        f = tmp_path / "data.json"
        f.write_text(json.dumps({"key": "value"}), encoding="utf-8")
        assert read_json(f) == {"key": "value"}

    def test_returns_none_on_invalid_json(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.json"
        f.write_text("not json {{{", encoding="utf-8")
        assert read_json(f) is None

    def test_returns_none_on_missing_file(self, tmp_path: Path) -> None:
        assert read_json(tmp_path / "nope.json") is None


class TestReadYaml:
    def test_parses_valid_yaml(self, tmp_path: Path) -> None:
        f = tmp_path / "config.yaml"
        f.write_text("key: value\nlist:\n  - a\n  - b", encoding="utf-8")
        result = read_yaml(f)
        assert result == {"key": "value", "list": ["a", "b"]}

    def test_returns_none_on_invalid_yaml(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.yaml"
        f.write_text("{{{{invalid", encoding="utf-8")
        assert read_yaml(f) is None


class TestPathByKind:
    def test_matches_exact_filename(self) -> None:
        result = path_by_kind(["/a/b/config.json", "/x/y/other.txt"], "config.json")
        assert result == Path("/a/b/config.json")

    def test_matches_stem_case_insensitive(self) -> None:
        result = path_by_kind(["/a/SOUL.md"], "soul")
        assert result == Path("/a/SOUL.md")

    def test_returns_none_when_not_found(self) -> None:
        assert path_by_kind(["/a/b.txt"], "missing.md") is None


class TestFindFile:
    def test_finds_existing_file(self, tmp_path: Path) -> None:
        (tmp_path / "sub").mkdir()
        target = tmp_path / "sub" / "file.txt"
        target.write_text("x", encoding="utf-8")
        assert find_file(tmp_path, "sub", "file.txt") == target

    def test_returns_none_for_missing(self, tmp_path: Path) -> None:
        assert find_file(tmp_path, "no", "such.txt") is None


class TestExtractEnvKeyNames:
    def test_extracts_known_keys(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text(
            "OPENAI_API_KEY=sk-xxx\nRANDOM_VAR=123\nANTHROPIC_API_KEY=ak-yyy\n",
            encoding="utf-8",
        )
        result = extract_env_key_names(env)
        names = [item["name"] for item in result]
        assert "OPENAI_API_KEY" in names
        assert "ANTHROPIC_API_KEY" in names
        assert "RANDOM_VAR" not in names

    def test_ignores_comments_and_empty_lines(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("# comment\n\nGROQ_API_KEY=gk-z\n", encoding="utf-8")
        result = extract_env_key_names(env)
        assert len(result) == 1
        assert result[0]["name"] == "GROQ_API_KEY"


class TestLoadSkillDirectories:
    def test_loads_skills_with_skill_md(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        skill_a = skills_dir / "deploy"
        skill_a.mkdir(parents=True)
        (skill_a / "SKILL.md").write_text("Deploy workflow", encoding="utf-8")
        skill_b = skills_dir / "review"
        skill_b.mkdir()
        (skill_b / "SKILL.md").write_text("Code review", encoding="utf-8")

        result = load_skill_directories(skills_dir, source="test")
        assert len(result) == 2
        names = {s["name"] for s in result}
        assert names == {"deploy", "review"}
        assert all(s["source"] == "test" for s in result)

    def test_skips_dirs_without_skill_md(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        (skills_dir / "empty").mkdir(parents=True)
        result = load_skill_directories(skills_dir, source="test")
        assert result == []


class TestMarkdownBulletsToMemory:
    def test_extracts_bullet_items(self) -> None:
        text = "- First bullet\n- Second bullet\n* Third"
        result = markdown_bullets_to_memory(text, category="mem")
        assert len(result) == 3
        assert result[0]["content"] == "First bullet"
        assert result[1]["content"] == "Second bullet"
        assert result[2]["content"] == "Third"
        assert all(item["category"] == "mem" for item in result)

    def test_fallback_whole_text_when_no_bullets(self) -> None:
        text = "This is a plain paragraph with no bullets."
        result = markdown_bullets_to_memory(text, category="note")
        assert len(result) == 1
        assert result[0]["content"] == text

    def test_empty_text_returns_empty(self) -> None:
        assert markdown_bullets_to_memory("", category="x") == []
        assert markdown_bullets_to_memory("   ", category="x") == []
