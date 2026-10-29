"""Leak detector: a password in the user position of a URL is a leak for any scheme, driver and user name.

A connection string names its service by scheme, and ``redis://:password@cache`` has no user name, ``postgresql+asyncpg``
a driver, ``socks5``, ``ssh`` and ``https`` are no database at all. A URL that carries no password, or a variable
reference where the password goes, is no leak.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.core.security.detection.leak_detector import redact_leaks, scan_for_leaks

_PASSWORD = "s3cr3tValue99"


class TestPasswordInTheUserPosition:
    @pytest.mark.parametrize(
        ("url", "label"),
        [
            (f"redis://:{_PASSWORD}@cache:6379/0", "database_url"),
            (f"REDIS_URL=redis://:{_PASSWORD}@cache:6379/0", "database_url"),
            (f"postgresql+asyncpg://app:{_PASSWORD}@db/x", "database_url"),
            (f"mysql+pymysql://app:{_PASSWORD}@db/x", "database_url"),
            (f"POSTGRES://app:{_PASSWORD}@db/x", "database_url"),
            (f"postgres://root:p@{_PASSWORD}@localhost:5432/prod", "database_url"),
            (f"https://deploy:{_PASSWORD}@git.example.com/org/repo.git", "url_credential"),
            (f"socks5://proxy:{_PASSWORD}@10.0.0.1:1080", "url_credential"),
            (f"ssh://deploy:{_PASSWORD}@host.example:22/srv", "url_credential"),
            (f"smtp://mailer:{_PASSWORD}@mail.example:587", "url_credential"),
            (f"mssql+pyodbc://sa:{_PASSWORD}@sql.internal/app", "url_credential"),
        ],
    )  # fmt: skip
    def test_the_url_is_a_leak_and_its_password_is_masked(self, url: str, label: str) -> None:
        assert scan_for_leaks(url) == [label]
        assert _PASSWORD not in redact_leaks(url)

    def test_a_database_url_is_reported_once(self) -> None:
        assert scan_for_leaks(f"postgres://app:{_PASSWORD}@db/x") == ["database_url"]


class TestNoPasswordNoLeak:
    @pytest.mark.parametrize(
        "text",
        [
            "ssh://git@github.com:22/org/repo.git",
            "https://example.com:8443/path/to/page",
            "http://localhost:3000/api/users/me",
            "postgres://db.internal:5432/app",
            "redis://cache.internal:6379/0",
            "socks5://10.0.0.1:1080",
            "mailto:alice@example.com",
            "see the section on a:b and then write to ops@example.com",
            "redis://localhost:6379 from Python? mail me: a@example.com",
        ],
    )  # fmt: skip
    def test_a_url_without_a_password_is_clean(self, text: str) -> None:
        assert scan_for_leaks(text) == []

    @pytest.mark.parametrize(
        "text",
        [
            "https://deploy:${REGISTRY_TOKEN}@registry.example/v2/",
            "socks5://proxy:$PROXY_PW@10.0.0.1:1080",
        ],
    )  # fmt: skip
    def test_a_variable_reference_in_place_of_the_password_is_clean(self, text: str) -> None:
        assert "url_credential" not in scan_for_leaks(text)


class TestMaskedPasswordIsNoLeak:
    """The redactor writes ``***`` where the password was: text it already redacted scans clean and stays as it is."""

    @pytest.mark.parametrize(
        "text",
        [
            "https://deploy:***@git.example.com/org/repo.git",
            "postgres://root:***@localhost:5432/prod",
            "redis://:***@cache:6379/0",
            "socks5://proxy:***@10.0.0.1:1080",
        ],
    )  # fmt: skip
    def test_a_masked_url_scans_clean_and_is_not_rewritten(self, text: str) -> None:
        assert scan_for_leaks(text) == []
        assert redact_leaks(text) == text

    def test_a_password_that_merely_starts_with_the_mask_is_still_a_leak(self) -> None:
        assert scan_for_leaks("https://deploy:***a1b2@git.example.com/org/repo.git") == ["url_credential"]
