"""URL credentials: the password of ``scheme://[user]:password@host`` is masked for any scheme and driver.

A connection string carries its credential in the URL, and tools print it in error messages, config dumps and
settings files whatever the service: ``redis://:password@cache`` has no user name, ``postgresql+asyncpg://`` names a
driver, and ``amqps``, ``mssql+pyodbc``, ``clickhouse``, ``ssh``, ``socks5``, ``smtp``, ``nats`` and ``kafka`` are
not in any fixed scheme list. The user name stays readable and the rest of the URL is kept; a URL without a
password and a repeated pass over an already masked URL are left as they are.
"""

from __future__ import annotations

import time

import pytest

from myrm_agent_harness.core.security.redact import redact_sensitive_text

_PASSWORD = "correct-horse-91-Zk3fQ9xL"

_URLS: dict[str, str] = {
    "redis-without-user": f"redis://:{_PASSWORD}@cache.internal:6379/0",
    "redis-with-user": f"redis://default:{_PASSWORD}@cache.internal:6379/0",
    "rediss": f"rediss://default:{_PASSWORD}@cache.internal:6380/0",
    "amqp": f"amqp://app:{_PASSWORD}@mq.internal:5672/vhost",
    "amqps": f"amqps://app:{_PASSWORD}@mq.internal:5671/vhost",
    "postgres-asyncpg": f"postgresql+asyncpg://app:{_PASSWORD}@db.internal:5432/app",
    "mysql-pymysql": f"mysql+pymysql://app:{_PASSWORD}@db.internal:3306/app",
    "mssql-pyodbc": f"mssql+pyodbc://sa:{_PASSWORD}@sql.internal/app?driver=ODBC+Driver+18",
    "clickhouse": f"clickhouse://default:{_PASSWORD}@ch.internal:9000/db",
    "ssh": f"ssh://deploy:{_PASSWORD}@host.example:22/srv",
    "socks5": f"socks5://proxy:{_PASSWORD}@10.0.0.1:1080",
    "smtp": f"smtp://mailer:{_PASSWORD}@mail.example:587",
    "nats": f"nats://svc:{_PASSWORD}@nats.internal:4222",
    "kafka": f"kafka://svc:{_PASSWORD}@broker.internal:9092",
    "https": f"https://deploy:{_PASSWORD}@registry.example/v2/",
}  # fmt: skip

_CONTEXTS: dict[str, str] = {
    "bare": "{url}",
    "env": "DATABASE_URL={url}",
    "sentence": "ConnectionError: cannot reach {url} (timeout after 5s)",
    "yaml": "services:\n  app:\n    url: {url}\n    retries: 3",
}  # fmt: skip


class TestPasswordIsMasked:
    @pytest.mark.parametrize("context", _CONTEXTS)
    @pytest.mark.parametrize("kind", _URLS)
    def test_password_is_replaced_and_everything_else_is_kept(self, kind: str, context: str) -> None:
        text = _CONTEXTS[context].format(url=_URLS[kind])
        assert redact_sensitive_text(text) == text.replace(_PASSWORD, "***")

    @pytest.mark.parametrize("kind", _URLS)
    def test_masking_twice_changes_nothing(self, kind: str) -> None:
        once = redact_sensitive_text(_URLS[kind])
        assert redact_sensitive_text(once) == once

    def test_two_urls_in_one_text_are_both_masked(self) -> None:
        text = f"primary={_URLS['redis-without-user']} replica={_URLS['postgres-asyncpg']}"
        assert redact_sensitive_text(text) == text.replace(_PASSWORD, "***")

    def test_user_name_stays_readable(self) -> None:
        assert redact_sensitive_text(_URLS["socks5"]) == "socks5://proxy:***@10.0.0.1:1080"

    def test_a_long_word_before_the_separator_does_not_hide_the_password(self) -> None:
        text = f"{'x' * 41}://app:{_PASSWORD}@host.example/path"
        assert redact_sensitive_text(text) == text.replace(_PASSWORD, "***")


class TestVariableReferencesAreKept:
    """A password written as a variable reference is a name, not a secret: compose and shell files stay readable."""

    @pytest.mark.parametrize(
        "text",
        [
            "REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0",
            "redis://default:${REDIS_PASSWORD}@redis:6379/0",
            "postgres://app:${POSTGRES_PASSWORD}@db/app",
            "postgresql+asyncpg://app:${DB_PASS}@db/app",
            "https://deploy:${REGISTRY_TOKEN}@registry.example/v2/",
            "socks5://proxy:$PROXY_PW@10.0.0.1:1080",
            "amqps://app:${MQ_PASS:?set it in .env}@mq.internal/vhost",
        ],
    )  # fmt: skip
    def test_reference_stays_readable(self, text: str) -> None:
        assert redact_sensitive_text(text) == text

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("redis://:$Secret123@cache:6379/0", "redis://:***@cache:6379/0"),
            ("redis://:${REDIS_PASSWORD}tail@cache:6379/0", "redis://:***@cache:6379/0"),
            ("postgres://app:pa$$word-91@db/app", "postgres://app:***@db/app"),
        ],
    )  # fmt: skip
    def test_a_literal_that_only_looks_like_a_reference_is_masked(self, text: str, expected: str) -> None:
        assert redact_sensitive_text(text) == expected


class TestUrlsWithoutPasswordAreKept:
    @pytest.mark.parametrize(
        "text",
        [
            "ssh://git@github.com:22/org/repo.git",
            "https://example.com:8443/path/to/page",
            "postgres://db.internal:5432/app",
            "redis://cache.internal:6379/0",
            "socks5://10.0.0.1:1080",
            "git@github.com:org/repo.git",
            "mailto:alice@example.com",
            "http://localhost:3000/api/users/me",
            "see the section on a:b and then write to ops@example.com",
        ],
    )  # fmt: skip
    def test_text_stays_readable(self, text: str) -> None:
        assert redact_sensitive_text(text) == text


class TestPasswordRunsToTheLastAt:
    """A password printed with a raw ``@`` is masked whole: ending at the first ``@`` leaves the rest beside the host."""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("postgres://root:p@ssw0rd123@localhost:5432/prod", "postgres://root:***@localhost:5432/prod"),
            ("mysql://app:Summer2024@Home!@db:3306/x", "mysql://app:***@db:3306/x"),
            ("redis://:Pass@word9@cache:6379/0", "redis://:***@cache:6379/0"),
            ("ssh://deploy:p@ss@host", "ssh://deploy:***@host"),
            ("socks5://user:abc@123456@10.0.0.1:1080", "socks5://user:***@10.0.0.1:1080"),
        ],
    )  # fmt: skip
    def test_the_whole_password_is_masked(self, text: str, expected: str) -> None:
        assert redact_sensitive_text(text) == expected

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("http://u:pw@h:80 mail me at a@b.c", "http://u:***@h:80 mail me at a@b.c"),
            ("redis://:pw12345@cache:6379/0 then a@b.c", "redis://:***@cache:6379/0 then a@b.c"),
            ('{"url":"https://u:pw12345@h","email":"a@b.c"}', '{"url":"https://u:***@h","email":"a@b.c"}'),
            ("[link](https://u:pw12345@h) and mail a@b.c", "[link](https://u:***@h) and mail a@b.c"),
            ("https://user:pw12345@example.com/path?email=a@b.c", "https://user:***@example.com/path?email=a@b.c"),
        ],
    )  # fmt: skip
    def test_text_after_the_url_is_not_swallowed(self, text: str, expected: str) -> None:
        assert redact_sensitive_text(text) == expected

    def test_a_dsn_is_masked_before_the_text_that_follows_it(self) -> None:
        text = "How do I connect to redis://localhost:6379 from Python? Mail a@example.com"
        assert redact_sensitive_text(text) == text


class TestScanCostStaysLinear:
    """A scheme may be any word, and the scan for one must not restart at every character of a long run.

    The scheme can only start at the beginning of a run of scheme characters, so a run is scanned once. A scheme
    that may start anywhere takes over a second on 16 000 characters here, the shipped one a few milliseconds; the
    budget sits between them with a wide margin on both sides.
    """

    _BUDGET_SECONDS = 0.5

    @pytest.mark.parametrize("unit", ["a", "a.", "a+", "a-", "a1", "ab:/", "http", "a://"])
    def test_run_of_scheme_characters(self, unit: str) -> None:
        text = unit * (16_000 // len(unit))
        start = time.process_time()
        redact_sensitive_text(text)
        assert time.process_time() - start < self._BUDGET_SECONDS


class TestDsnPrefixScanIsBounded:
    """``redis://:`` repeated with no ``@`` makes every start scan the rest of the run; the password span is capped.

    Unbounded, 32 000 characters take about 0.7 seconds here, bounded about 0.15; the budget sits between them.
    """

    _BUDGET_SECONDS = 0.4

    @pytest.mark.parametrize("unit", ["redis://:", "redis://x:", "postgres://:p"])
    def test_repeated_dsn_prefix(self, unit: str) -> None:
        text = unit * (32_000 // len(unit))
        start = time.process_time()
        redact_sensitive_text(text)
        assert time.process_time() - start < self._BUDGET_SECONDS
