"""Unit tests for leak_detector — redaction behavior and entropy analysis.

Covers:
  - Several credentials in one text; redaction is idempotent
  - Shannon entropy analysis (unknown credential formats)
  - log_leaks and edge cases
"""

from __future__ import annotations

from myrm_agent_harness.agent.security.detection.leak_detector import redact_leaks, scan_for_leaks

# ===================================================================
# 1. Multiple pattern detection
# ===================================================================


class TestMultiplePatterns:
    """Detect multiple credential types in single content."""

    def test_api_key_plus_database_url(self) -> None:
        content = "sk-" + "a" * 48 + " postgres://u:p@host/db"
        matches = scan_for_leaks(content)
        assert "openai_key" in matches
        assert "database_url" in matches

    def test_env_plus_api_key(self) -> None:
        content = "API_KEY=verylongsecretvalue1234567890 and ghp_" + "a" * 36
        matches = scan_for_leaks(content)
        assert "github_token" in matches
        assert "env_credential" in matches


class TestRedactionIsIdempotent:
    """Persisted text is scanned again (consolidation, restore); an earlier redaction is not a secret."""

    def test_env_and_json_values_already_redacted_are_left_alone(self) -> None:
        env_once = redact_leaks("API_KEY=verylongsecretvalue1234567890")
        json_once = redact_leaks('{"password": "verylongsecretvalue1234567890"}')

        assert scan_for_leaks(env_once) == []
        assert redact_leaks(env_once) == env_once
        assert scan_for_leaks(json_once) == []
        assert redact_leaks(json_once) == json_once


# ===================================================================
# 2. Shannon entropy detection
# ===================================================================


class TestShannonEntropy:
    """High-entropy token detection for unknown credential formats."""

    def test_bare_high_entropy_token(self) -> None:
        assert "high_entropy_token" in scan_for_leaks("Found: aB3xK9mW2pQ7vL4nR8sT1yU6hD0jF5cG")

    def test_another_high_entropy(self) -> None:
        assert "high_entropy_token" in scan_for_leaks("Key X7k9M2pQvL4nR8s1T6hD0jF5cGaB3xK9")

    def test_uuid_not_flagged(self) -> None:
        assert "high_entropy_token" not in scan_for_leaks("id: 550e8400-e29b-41d4-a716-446655440000")

    def test_git_hash_not_flagged(self) -> None:
        assert "high_entropy_token" not in scan_for_leaks("commit a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0")

    def test_sha256_not_flagged(self) -> None:
        assert "high_entropy_token" not in scan_for_leaks(
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )

    def test_url_path_not_flagged(self) -> None:
        assert "high_entropy_token" not in scan_for_leaks("https://example.com/docs/2024-report-a1b2c3d4e5f6g7h8.pdf")

    def test_base64_with_special_chars_not_flagged(self) -> None:
        assert "high_entropy_token" not in scan_for_leaks("SGVsbG8gV29ybGQhIFRo+aXMgaXMgYS/B0ZXN0Lg==")

    def test_short_token_not_flagged(self) -> None:
        assert "high_entropy_token" not in scan_for_leaks("token: aB3xK9mW2pQ7vL4")

    def test_all_alpha_not_flagged(self) -> None:
        assert "high_entropy_token" not in scan_for_leaks("word: abcdefghijklmnopqrstuvwxyz")

    def test_redaction_preserves_head_tail(self) -> None:
        token = "aB3xK9mW2pQ7vL4nR8sT1yU6hD0jF5cG"
        result = redact_leaks(f"Cred: {token} end")
        assert token not in result
        assert "aB3xK9" in result
        assert "F5cG" in result
        assert "[REDACTED:high_entropy_token]" in result

    def test_known_prefix_not_double_detected(self) -> None:
        key = "ghp_" + "a" * 36
        matches = scan_for_leaks(f"Token: {key}")
        assert "github_token" in matches

    def test_non_ascii_content_not_flagged(self) -> None:
        """Non-ASCII content (CJK, etc.) should not trigger entropy detection."""
        chinese = "## 明天北京到上海卧铺票查询结果 共找到8趟有卧铺的列车\n| 1461 | 北京 | 上海 | 硬卧 | 283.5元 | 1张 |"
        assert "high_entropy_token" not in scan_for_leaks(chinese)

    def test_japanese_content_not_flagged(self) -> None:
        content = "東京から大阪まで新幹線で2時間30分かかります。料金は13870円です。"
        assert "high_entropy_token" not in scan_for_leaks(content)

    def test_anchored_wikilink_and_pipes_not_flagged(self) -> None:
        """Markdown wikilinks with anchors and aliases should not trigger entropy false positive."""
        content = "Reference [[vault/custom-note#Section-42|Display Label]]"
        assert "high_entropy_token" not in scan_for_leaks(content)
        assert redact_leaks(content) == content


# ===================================================================
# 3. log_leaks and edge cases
# ===================================================================


class TestLogLeaksAndEdgeCases:
    """Cover log_leaks function and internal edge cases."""

    def test_log_leaks_no_exception(self) -> None:
        from myrm_agent_harness.agent.security.detection.leak_detector import log_leaks

        log_leaks(["openai_key"], "sk-" + "a" * 48)

    def test_log_leaks_long_content_truncated(self) -> None:
        from myrm_agent_harness.agent.security.detection.leak_detector import log_leaks

        log_leaks(["high_entropy_token"], "x" * 500)
