"""Unit tests for leak_detector — credential leak detection by pattern.

Covers:
  - 30+ prefix-based API key patterns (positive + negative)
  - Structural formats (JWT, PEM key headers, database URLs)
  - Context-aware patterns (ENV, JSON, Auth header)
  - False-positive resistance and placeholder exclusion for context patterns
  - Smart redaction (short/long tokens, pattern labels)
"""

from __future__ import annotations

from myrm_agent_harness.agent.security.detection.leak_detector import redact_leaks, scan_for_leaks
from tests.support.fake_secrets import jwt_shaped

# ===================================================================
# 1. Prefix-based API key detection
# ===================================================================


class TestApiKeyPatterns:
    """Prefix-based API key detection — one test per provider."""

    # --- Payment ---

    def test_stripe_live_key(self) -> None:
        assert "stripe_key" in scan_for_leaks("sk_live_" + "a" * 24)

    def test_stripe_test_key(self) -> None:
        assert "stripe_key" in scan_for_leaks("sk_test_" + "a" * 24)

    def test_stripe_restricted_key(self) -> None:
        assert "stripe_restricted" in scan_for_leaks("rk_live_" + "a" * 24)

    # --- AI / LLM ---

    def test_openai_key(self) -> None:
        assert "openai_key" in scan_for_leaks("sk-" + "a" * 48)

    def test_anthropic_key(self) -> None:
        assert "anthropic_key" in scan_for_leaks("sk-ant-" + "a" * 32)

    def test_google_key(self) -> None:
        assert "google_key" in scan_for_leaks("AIza" + "a" * 35)

    def test_huggingface_token(self) -> None:
        assert "huggingface_token" in scan_for_leaks("hf_" + "a" * 34)

    def test_replicate_token(self) -> None:
        assert "replicate_token" in scan_for_leaks("r8_" + "a" * 36)

    def test_perplexity_key(self) -> None:
        assert "perplexity_key" in scan_for_leaks("pplx-" + "a" * 48)

    def test_groq_key(self) -> None:
        assert "groq_key" in scan_for_leaks("gsk_" + "a" * 48)

    def test_databricks_token(self) -> None:
        assert "databricks_token" in scan_for_leaks("dapi" + "a" * 32)

    # --- Cloud ---

    def test_aws_access_key(self) -> None:
        assert "aws_access_key" in scan_for_leaks("AKIAIOSFODNN7EXAMPLE")

    def test_aws_session_token(self) -> None:
        # STS temporary session credentials — same shape as AKIA but ASIA-prefixed;
        # the entropy fallback does not catch the 20-char mixed case, so a dedicated pattern must.
        assert "aws_session_token" in scan_for_leaks("ASIAIOSFODNN7EXAMPLE")

    def test_asia_plain_word_not_flagged(self) -> None:
        # Benign prose mentioning the ASIA region must not trip the pattern.
        assert "aws_session_token" not in scan_for_leaks("deploy to ASIA region servers")

    def test_digitalocean_token(self) -> None:
        assert "digitalocean_token" in scan_for_leaks("dop_v1_" + "a" * 64)

    def test_vercel_token(self) -> None:
        assert "vercel_token" in scan_for_leaks("vercel_" + "a" * 24)

    def test_supabase_key(self) -> None:
        assert "supabase_key" in scan_for_leaks("sbp_" + "a" * 40)

    def test_cloudflare_token(self) -> None:
        assert "cloudflare_token" in scan_for_leaks("cf_" + "a" * 37)

    # --- DevOps / VCS ---

    def test_github_token(self) -> None:
        assert "github_token" in scan_for_leaks("ghp_" + "a" * 36)

    def test_github_pat(self) -> None:
        assert "github_pat" in scan_for_leaks("github_pat_" + "a" * 22)

    def test_gitlab_token(self) -> None:
        assert "gitlab_token" in scan_for_leaks("glpat-" + "a" * 20)

    def test_npm_token(self) -> None:
        assert "npm_token" in scan_for_leaks("npm_" + "a" * 36)

    def test_pypi_token(self) -> None:
        assert "pypi_token" in scan_for_leaks("pypi-" + "a" * 36)

    # --- Communication ---

    def test_slack_token(self) -> None:
        assert "slack_token" in scan_for_leaks("xoxb-" + "a" * 10)

    def test_telegram_bot(self) -> None:
        assert "telegram_bot" in scan_for_leaks("123456789:" + "a" * 35)

    def test_sendgrid_key(self) -> None:
        assert "sendgrid_key" in scan_for_leaks("SG." + "a" * 22 + "." + "a" * 43)

    def test_twilio_key(self) -> None:
        assert "twilio_key" in scan_for_leaks("SK" + "a" * 32)

    # --- Media / AI services ---

    def test_elevenlabs_key(self) -> None:
        assert "elevenlabs_key" in scan_for_leaks("el_" + "a" * 32)

    def test_fal_key(self) -> None:
        assert "fal_key" in scan_for_leaks("fal_" + "a" * 32)

    # --- Search / Web ---

    def test_tavily_key(self) -> None:
        assert "tavily_key" in scan_for_leaks("tvly-" + "a" * 32)

    def test_firecrawl_key(self) -> None:
        assert "firecrawl_key" in scan_for_leaks("fc-" + "a" * 32)

    def test_browserbase_key(self) -> None:
        assert "browserbase_key" in scan_for_leaks("bb_live_" + "a" * 32)


# ===================================================================
# 2. Structural format detection
# ===================================================================


class TestStructuralPatterns:
    """JWT, PEM, database URL detection."""

    def test_jwt_token(self) -> None:
        assert "jwt_token" in scan_for_leaks(jwt_shaped("hbGciOiJIUzI1NiJ9", "zdWIiOiIxMjM0In0", "abc123def456"))

    def test_pem_rsa_key(self) -> None:
        assert "pem_private_key" in scan_for_leaks("-----BEGIN RSA PRIVATE KEY-----")

    def test_pem_ec_key(self) -> None:
        assert "pem_private_key" in scan_for_leaks("-----BEGIN EC PRIVATE KEY-----")

    def test_pem_openssh_key(self) -> None:
        assert "pem_private_key" in scan_for_leaks("-----BEGIN OPENSSH PRIVATE KEY-----")

    def test_pem_generic_key(self) -> None:
        assert "pem_private_key" in scan_for_leaks("-----BEGIN PRIVATE KEY-----")

    def test_postgres_url(self) -> None:
        assert "database_url" in scan_for_leaks("postgres://user:pass@host:5432/db")

    def test_mysql_url(self) -> None:
        assert "database_url" in scan_for_leaks("mysql://admin:secret@db.example.com/app")

    def test_mongodb_srv_url(self) -> None:
        assert "database_url" in scan_for_leaks("mongodb+srv://u:p@cluster.mongodb.net/db")

    def test_redis_url(self) -> None:
        assert "database_url" in scan_for_leaks("redis://default:pw@redis.example.com:6379")

    def test_amqp_url(self) -> None:
        assert "database_url" in scan_for_leaks("amqps://user:pass@rabbitmq.example.com/vhost")


# ===================================================================
# 3. Context-aware patterns (ENV, JSON, Auth header)
# ===================================================================


class TestContextPatterns:
    """ENV assignment, JSON field, and Auth header detection."""

    def test_env_assignment(self) -> None:
        content = "export API_KEY=abcdef1234567890abcdef1234567890"
        assert "env_credential" in scan_for_leaks(content)

    def test_env_secret_key(self) -> None:
        content = "SECRET_KEY=supersecretvalue1234567890abc"
        assert "env_credential" in scan_for_leaks(content)

    def test_env_password(self) -> None:
        content = "PASSWORD=MyVeryLongPassword123!"
        assert "env_credential" in scan_for_leaks(content)

    def test_env_with_quotes(self) -> None:
        content = "TOKEN='abcdef1234567890abcdef1234567890'"
        assert "env_credential" in scan_for_leaks(content)

    def test_env_short_value_ignored(self) -> None:
        content = "API_KEY=short"
        assert "env_credential" not in scan_for_leaks(content)

    def test_env_placeholder_ignored(self) -> None:
        content = "API_KEY=your_api_key_here"
        assert "env_credential" not in scan_for_leaks(content)

    def test_env_placeholder_changeme(self) -> None:
        content = "SECRET_KEY=changeme"
        assert "env_credential" not in scan_for_leaks(content)

    def test_env_placeholder_variable(self) -> None:
        content = "API_KEY=${SOME_ENV_VAR}"
        assert "env_credential" not in scan_for_leaks(content)

    def test_json_field(self) -> None:
        content = '{"apiKey": "abcdef1234567890abcdef1234567890"}'
        assert "json_credential" in scan_for_leaks(content)

    def test_json_secret(self) -> None:
        content = '{"secret": "reallylongsecretvalue1234567890"}'
        assert "json_credential" in scan_for_leaks(content)

    def test_json_password(self) -> None:
        content = '{"password": "MyDatabasePassword123!"}'
        assert "json_credential" in scan_for_leaks(content)

    def test_json_short_value_ignored(self) -> None:
        content = '{"apiKey": "test"}'
        assert "json_credential" not in scan_for_leaks(content)

    def test_json_placeholder_ignored(self) -> None:
        content = '{"token": "your_token_here_placeholder"}'
        assert "json_credential" not in scan_for_leaks(content)

    def test_auth_header_bearer(self) -> None:
        content = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        assert "auth_header_credential" in scan_for_leaks(content)

    def test_auth_header_basic(self) -> None:
        content = "Authorization: Basic dXNlcjpwYXNzd29yZDEyMzQ1Njc4OQ=="
        assert "auth_header_credential" in scan_for_leaks(content)

    def test_auth_header_token(self) -> None:
        content = "Authorization: Token abcdef1234567890abcdef"
        assert "auth_header_credential" in scan_for_leaks(content)

    def test_auth_header_lowercase(self) -> None:
        content = "authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        assert "auth_header_credential" in scan_for_leaks(content)

    def test_auth_header_uppercase(self) -> None:
        content = "AUTHORIZATION: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        assert "auth_header_credential" in scan_for_leaks(content)

    def test_auth_header_mixed_case(self) -> None:
        content = "aUtHoRiZaTiOn: Token abcdef1234567890abcdef"
        assert "auth_header_credential" in scan_for_leaks(content)


# ===================================================================
# 4. False positive resistance
# ===================================================================


class TestFalsePositives:
    """Ensure common safe content is not flagged."""

    def test_normal_text(self) -> None:
        assert scan_for_leaks("This is just normal text") == []

    def test_short_sk_prefix(self) -> None:
        assert scan_for_leaks("sk-short") == []

    def test_code_snippet(self) -> None:
        assert scan_for_leaks("def get_api_key(): return config['key']") == []

    def test_empty_input(self) -> None:
        assert scan_for_leaks("") == []

    def test_env_example_values(self) -> None:
        assert scan_for_leaks("API_KEY=example") == []

    def test_env_todo_placeholder(self) -> None:
        assert scan_for_leaks("SECRET=TODO") == []

    def test_json_null_value(self) -> None:
        assert scan_for_leaks('{"token": "null"}') == []

    def test_json_test_value(self) -> None:
        assert scan_for_leaks('{"password": "test"}') == []

    def test_url_without_credentials(self) -> None:
        assert scan_for_leaks("https://example.com/api/v1") == []


# ===================================================================
# 5. Smart redaction
# ===================================================================


class TestSmartRedaction:
    """Smart redaction preserves first 6 / last 4 for long tokens."""

    def test_long_token_preserves_head_tail(self) -> None:
        key = "sk_live_" + "a" * 24
        result = redact_leaks(f"Key: {key}")
        assert "sk_liv" in result
        assert result.endswith(" [REDACTED:stripe_key]")
        assert key not in result

    def test_short_token_fully_masked(self) -> None:
        result = redact_leaks("-----BEGIN PRIVATE KEY-----")
        assert "[REDACTED:pem_private_key]" in result

    def test_medium_token_preserves_head_tail(self) -> None:
        result = redact_leaks("AKIAIOSFODNN7EXAMPLE")
        assert "[REDACTED:aws_access_key]" in result
        assert "AKIAIO" in result
        assert "MPLE" in result

    def test_pattern_label_in_output(self) -> None:
        result = redact_leaks("sk-ant-" + "a" * 32)
        assert "[REDACTED:anthropic_key]" in result

    def test_preserves_surrounding_text(self) -> None:
        key = "sk_live_" + "a" * 24
        result = redact_leaks(f"before {key} after")
        assert result.startswith("before ")
        assert "after" in result

    def test_multiple_redactions(self) -> None:
        content = "sk_live_" + "a" * 24 + " and AKIAIOSFODNN7EXAMPLE"
        result = redact_leaks(content)
        assert "[REDACTED:stripe_key]" in result
        assert "[REDACTED:aws_access_key]" in result

    def test_no_change_clean_text(self) -> None:
        content = "This is safe text"
        assert redact_leaks(content) == content

    def test_empty_input(self) -> None:
        assert redact_leaks("") == ""

    def test_env_redaction(self) -> None:
        content = "export API_KEY=abcdef1234567890abcdef1234567890"
        result = redact_leaks(content)
        assert "[REDACTED:env_credential]" in result
        assert "abcdef1234567890abcdef1234567890" not in result

    def test_json_redaction(self) -> None:
        content = '{"secret": "reallylongsecretvalue1234567890"}'
        result = redact_leaks(content)
        assert "[REDACTED:json_credential]" in result
        assert "reallylongsecretvalue1234567890" not in result

    def test_auth_header_redaction(self) -> None:
        content = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        result = redact_leaks(content)
        assert "[REDACTED:" in result

    def test_env_placeholder_not_redacted(self) -> None:
        content = "API_KEY=your_api_key_here"
        assert redact_leaks(content) == content

    def test_json_placeholder_not_redacted(self) -> None:
        content = '{"token": "your_token_here_placeholder"}'
        assert redact_leaks(content) == content

    def test_env_short_credential_fully_masked(self) -> None:
        content = "API_KEY=aB3xK9mW2pQ7vL4n"
        result = redact_leaks(content)
        assert "[REDACTED:env_credential]" in result
        assert "***..." not in result
