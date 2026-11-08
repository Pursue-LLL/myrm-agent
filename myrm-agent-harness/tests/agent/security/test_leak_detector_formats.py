"""Unit tests for leak_detector — provider and infrastructure credential formats.

Covers:
  - OpenAI project keys (sk-proj-)
  - Compound ENV variable names
  - Blockchain patterns (Ethereum addresses, mnemonic phrases)
  - Cloud infrastructure patterns
  - PEM private key blocks (multiline redaction)
"""

from __future__ import annotations

from myrm_agent_harness.agent.security.detection.leak_detector import redact_leaks, scan_for_leaks
from tests.support.fake_secrets import openai_style_key

# ===================================================================
# 1. OpenAI new key format (sk-proj-)
# ===================================================================


class TestOpenAINewFormat:
    """OpenAI project-scoped keys with sk-proj- prefix."""

    def test_sk_proj_key(self) -> None:
        key = "sk-proj-" + "a" * 48
        assert "openai_key" in scan_for_leaks(key)

    def test_sk_proj_mixed_case(self) -> None:
        key = openai_style_key("proj-aB3xK9mW2pQ7vL4nR8sT1yU6hD0jF5cGaB3xK9mW2pQ7vL4n")
        assert "openai_key" in scan_for_leaks(key)

    def test_sk_proj_with_underscores(self) -> None:
        key = "sk-proj-abc_def_1234567890_abcdef1234567890_abcdef12345678"
        assert "openai_key" in scan_for_leaks(key)

    def test_sk_proj_redaction(self) -> None:
        key = "sk-proj-" + "a" * 48
        result = redact_leaks(f"Key: {key}")
        assert key not in result
        assert "[REDACTED:openai_key]" in result


# ===================================================================
# 2. Compound ENV variable names
# ===================================================================


class TestCompoundEnvVars:
    """ENV variables with prefixed sensitive keywords."""

    def test_custom_token(self) -> None:
        assert "env_credential" in scan_for_leaks("CUSTOM_TOKEN=a9f8b2c1e7d4k6m3p0q5r8s1")

    def test_my_api_key(self) -> None:
        assert "env_credential" in scan_for_leaks("MY_API_KEY=longsecretvalue1234567890")

    def test_app_secret(self) -> None:
        assert "env_credential" in scan_for_leaks("APP_SECRET=verylongsecretvalue1234")

    def test_db_password(self) -> None:
        assert "env_credential" in scan_for_leaks("DB_PASSWORD=supersecretdbpass123!")

    def test_auth_token_prefixed(self) -> None:
        assert "env_credential" in scan_for_leaks("GITHUB_AUTH_TOKEN=ghp_placeholder_long_enough_val")

    def test_compound_placeholder_not_flagged(self) -> None:
        assert "env_credential" not in scan_for_leaks("CUSTOM_TOKEN=your_token_here")

    def test_compound_short_value_not_flagged(self) -> None:
        assert "env_credential" not in scan_for_leaks("CUSTOM_TOKEN=short")


# ===================================================================
# 3. Blockchain patterns
# ===================================================================


class TestBlockchainPatterns:
    """Blockchain address and mnemonic detection."""

    def test_ethereum_address(self) -> None:
        assert "ethereum_address" in scan_for_leaks("Wallet: 0x742d35Cc6634C0532925a3b844Bc9e7595f2bD8E")

    def test_ethereum_address_lowercase(self) -> None:
        assert "ethereum_address" in scan_for_leaks("0xde0b295669a9fd93d5f28d9ec85e40f4cb697bae")

    def test_ethereum_address_too_short(self) -> None:
        assert "ethereum_address" not in scan_for_leaks("0x742d35Cc6634C053")

    def test_ethereum_address_redaction(self) -> None:
        result = redact_leaks("Addr: 0x742d35Cc6634C0532925a3b844Bc9e7595f2bD8E")
        assert "0x742d" in result
        assert "[REDACTED:ethereum_address]" in result
        assert "0x742d35Cc6634C0532925a3b844Bc9e7595f2bD8E" not in result

    def test_mnemonic_with_recovery_keyword(self) -> None:
        assert "mnemonic_phrase" in scan_for_leaks(
            "recovery phrase: abandon ability able about above absent absorb abstract absurd abuse access accident"
        )

    def test_mnemonic_with_seed_keyword(self) -> None:
        assert "mnemonic_phrase" in scan_for_leaks(
            "seed words = abandon ability able about above absent absorb abstract absurd abuse access accident"
        )

    def test_mnemonic_with_mnemonic_keyword(self) -> None:
        assert "mnemonic_phrase" in scan_for_leaks(
            'mnemonic: "abandon ability able about above absent absorb abstract absurd abuse access accident"'
        )

    def test_mnemonic_24_words(self) -> None:
        words = " ".join(["abandon"] * 24)
        assert "mnemonic_phrase" in scan_for_leaks(f"mnemonic: {words}")

    def test_mnemonic_without_context_not_flagged(self) -> None:
        assert "mnemonic_phrase" not in scan_for_leaks(
            "abandon ability able about above absent absorb abstract absurd abuse access accident"
        )

    def test_mnemonic_redaction(self) -> None:
        content = (
            "recovery phrase: abandon ability able about above absent absorb abstract absurd abuse access accident"
        )
        result = redact_leaks(content)
        assert "[REDACTED:mnemonic_phrase]" in result
        assert "abandon ability" not in result


# ===================================================================
# 4. Cloud infrastructure patterns
# ===================================================================


class TestCloudInfraPatterns:
    """Azure Storage Key and Discord Webhook detection."""

    def test_azure_storage_key(self) -> None:
        import base64

        key = base64.b64encode(b"a" * 64).decode()
        content = f"DefaultEndpointsProtocol=https;AccountName=myaccount;AccountKey={key};"
        assert "azure_storage_key" in scan_for_leaks(content)

    def test_azure_storage_key_redaction(self) -> None:
        import base64

        key = base64.b64encode(b"a" * 64).decode()
        content = f"DefaultEndpointsProtocol=https;AccountName=myaccount;AccountKey={key};"
        result = redact_leaks(content)
        assert "[REDACTED:azure_storage_key]" in result

    def test_discord_webhook(self) -> None:
        url = "https://discord.com/api/webhooks/1234567890123456789/" + "a" * 68
        assert "discord_webhook" in scan_for_leaks(url)

    def test_discord_webhook_discordapp(self) -> None:
        url = "https://discordapp.com/api/webhooks/1234567890123456789/" + "a" * 68
        assert "discord_webhook" in scan_for_leaks(url)

    def test_discord_webhook_redaction(self) -> None:
        url = "https://discord.com/api/webhooks/1234567890123456789/" + "a" * 68
        result = redact_leaks(url)
        assert "[REDACTED:discord_webhook]" in result

    def test_discord_bot_token(self) -> None:
        assert "discord_bot_token" in scan_for_leaks("MTI3NjU0MzIxMDk4.O1dBmQ.Rv-N3456789abcdefghijklmno")

    def test_discord_bot_token_longer(self) -> None:
        assert "discord_bot_token" in scan_for_leaks("MTI3NjU0MzIxMDk4NTIwNjU2MA.GpfL_n.abcdefghijklmnopqrstuvwxyz012")

    def test_discord_bot_token_redaction(self) -> None:
        token = "MTI3NjU0MzIxMDk4.O1dBmQ.Rv-N3456789abcdefghijklmno"
        result = redact_leaks(f"Bot: {token}")
        assert token not in result
        assert "[REDACTED:discord_bot_token]" in result

    def test_shopify_token(self) -> None:
        assert "shopify_token" in scan_for_leaks("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")

    def test_shopify_shared_secret(self) -> None:
        assert "shopify_shared_secret" in scan_for_leaks("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")

    def test_shopify_redaction(self) -> None:
        token = "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"
        result = redact_leaks(f"Token: {token}")
        assert "[REDACTED:shopify_token]" in result
        assert token not in result


# ===================================================================
# 5. PEM block-level redaction (multiline private key blocks)
# ===================================================================


class TestPemBlockRedaction:
    """Ensure entire PEM/SSH private key blocks are fully redacted."""

    _RSA_PEM = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC7s0Z1GZHVYvKE\n"
        "XnOJQhE1Lf4MJ7c5zVXYwR8mK3pN9AqD6bTPjHv2QkGxNl0DP/RzN6wVxyzAaBT\n"
        "gfQ4HrJ8kVEyLmTFN7P3qZ0J5B8KsVrU2LDo7TG0nnXKVzPMCK5N9xNz1R8rqXw\n"
        "-----END RSA PRIVATE KEY-----"
    )

    _OPENSSH_PEM = (
        "-----BEGIN OPENSSH PRIVATE KEY-----\n"
        "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW\n"
        "QyNTUxOQAAACBGMGNyL2FiY2RlZmdoaWprbG1ub3BxcnN0dXZ3eHl6AAAAIMAAAAMHAA\n"
        "-----END OPENSSH PRIVATE KEY-----"
    )

    _EC_PEM = (
        "-----BEGIN EC PRIVATE KEY-----\n"
        "MHQCAQEEIODg7G/Q1E0fR2Kv5U1F+r0O5LbQ9Gp4N2yEJm8v5nK+oAcGBSuBBAA\n"
        "-----END EC PRIVATE KEY-----"
    )

    _GENERIC_PEM = (
        "-----BEGIN PRIVATE KEY-----\n"
        "MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC7s0Z1GZHVYvKE\n"
        "-----END PRIVATE KEY-----"
    )

    def test_rsa_block_fully_redacted(self) -> None:
        result = redact_leaks(self._RSA_PEM)
        assert "MIIEvg" not in result
        assert "XnOJQh" not in result
        assert "DP/RzN6" not in result
        assert "pem_private_key_block:RSA" in result

    def test_openssh_block_fully_redacted(self) -> None:
        result = redact_leaks(self._OPENSSH_PEM)
        assert "b3Blbn" not in result
        assert "QyNTUx" not in result
        assert "pem_private_key_block:OPENSSH" in result

    def test_ec_block_fully_redacted(self) -> None:
        result = redact_leaks(self._EC_PEM)
        assert "MHQCAQEEIODg" not in result
        assert "pem_private_key_block:EC" in result

    def test_generic_block_fully_redacted(self) -> None:
        result = redact_leaks(self._GENERIC_PEM)
        assert "MIIEvg" not in result
        assert "pem_private_key_block" in result

    def test_pem_block_with_surrounding_text(self) -> None:
        content = f"Config file:\n{self._RSA_PEM}\nEnd of config"
        result = redact_leaks(content)
        assert "Config file:" in result
        assert "End of config" in result
        assert "MIIEvg" not in result

    def test_pem_block_with_slash_lines_not_leaked(self) -> None:
        """Regression: lines containing '/' were skipped by entropy check."""
        pem = (
            "-----BEGIN PRIVATE KEY-----\n"
            "MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC7s0Z1GZHVYvKE\n"
            "XnOJQhE1Lf4MJ7c5zVXYwR8mK3pN9AqD6bTPjHv2QkGxNl0DP/RzN6wVxyzAaBT\n"
            "-----END PRIVATE KEY-----"
        )
        result = redact_leaks(pem)
        # The line with '/' must NOT leak
        assert "DP/RzN6wVxyzAaBT" not in result

    def test_no_pem_text_unaffected(self) -> None:
        content = "User prefers dark mode and uses RSA authentication"
        assert redact_leaks(content) == content

    def test_scan_still_detects_pem(self) -> None:
        matches = scan_for_leaks(self._RSA_PEM)
        assert "pem_private_key" in matches
