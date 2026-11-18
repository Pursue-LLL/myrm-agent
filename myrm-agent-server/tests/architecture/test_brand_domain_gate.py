"""Architecture tests on tracked text files: brand domains.

Retired brand domains appear nowhere, the harness names no brand domain, and every host in a URL or an email address
that carries the product name is either the official domain or a reserved name.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_HARNESS_SOURCES = "myrm-agent-harness/src"
_MAX_REPORTED_HITS = 20

# The domains and the samples are assembled from fragments so this file does not match itself.
_PRODUCT_NAME = "myrm"
_LEGACY_DOMAIN = _PRODUCT_NAME + ".ai"
_LEGACY_GITHUB_ORG = "github.com/" + _PRODUCT_NAME + "-ai"
_OFFICIAL_DOMAIN = _PRODUCT_NAME + "agent.ai"

# A boundary is an explicit non-word class rather than \b, which `git grep -E` does not read the same way on every
# platform. A dot may carry backslashes, which is how a domain is written inside a regular expression or a string
# literal that holds one.
_BEFORE = r"(^|[^A-Za-z0-9_])"
_AFTER = r"([^A-Za-z0-9_]|$)"
_DOT = r"\\*\."


def _alternatives(*names: str) -> str:
    return _BEFORE + "(" + "|".join(name.replace(".", _DOT) for name in names) + ")" + _AFTER


_LEGACY_PATTERN = _alternatives(_LEGACY_DOMAIN, _LEGACY_GITHUB_ORG)
_ANY_BRAND_DOMAIN_PATTERN = _alternatives(_LEGACY_DOMAIN, _LEGACY_GITHUB_ORG, _OFFICIAL_DOMAIN)

# Hosts of a URL or an email address that carry the product name. The git pattern only prefilters candidate lines; the
# grammar reads the whole host, because the name can sit anywhere in it. The reserved names are the ones no one can
# register, which is what makes them safe in examples and tests.
_HOST_PREFILTER = rf"(https?://|@)[A-Za-z0-9.-]*{_PRODUCT_NAME}"
_HOST_GRAMMAR = re.compile(r"(?:https?://|@)((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,})", re.IGNORECASE)
_RESERVED_SUFFIXES = (".local", ".example", ".example.com")

_LEGACY_CASES = [
    pytest.param(f"see https://{_LEGACY_DOMAIN}/pricing", True, id="url"),
    pytest.param(f"see https://app.{_LEGACY_DOMAIN}/chat", True, id="subdomain"),
    pytest.param(f"mail to ops@{_LEGACY_DOMAIN}", True, id="email"),
    pytest.param(f"{_LEGACY_DOMAIN} is retired", True, id="at-line-start"),
    pytest.param(f"retired: {_LEGACY_DOMAIN}", True, id="at-line-end"),
    pytest.param(f"clone https://{_LEGACY_GITHUB_ORG}/repo", True, id="legacy-github-org"),
    pytest.param(_LEGACY_DOMAIN.replace(".", "\\."), True, id="escaped-in-a-regular-expression"),
    pytest.param(_LEGACY_DOMAIN.replace(".", "\\\\."), True, id="escaped-in-a-string-holding-a-regular-expression"),
    pytest.param(f"see https://{_OFFICIAL_DOMAIN}/docs", False, id="official-domain"),
    pytest.param(f"see https://x{_LEGACY_DOMAIN}/x", False, id="longer-name-before"),
    pytest.param(f"see https://{_LEGACY_DOMAIN}x/x", False, id="longer-name-after"),
    pytest.param("clone https://github.com/Pursue-LLL/myrm-agent", False, id="current-github-repo"),
]

_ANY_BRAND_CASES = [
    pytest.param(f"see https://{_LEGACY_DOMAIN}/x", True, id="legacy-domain"),
    pytest.param(f"see https://docs.{_OFFICIAL_DOMAIN}/docs", True, id="official-subdomain"),
    pytest.param(f"mail to noreply@{_OFFICIAL_DOMAIN}", True, id="official-email"),
    pytest.param("see https://example.com/docs", False, id="other-domain"),
    pytest.param("clone https://github.com/Pursue-LLL/myrm-agent", False, id="repository-name"),
]

_HOST_CASES = [
    pytest.param(f"https://{_OFFICIAL_DOMAIN}/docs", [], id="official-domain"),
    pytest.param(f"https://docs.{_OFFICIAL_DOMAIN}/docs", [], id="official-subdomain"),
    pytest.param(f"noreply@{_OFFICIAL_DOMAIN}", [], id="official-email"),
    pytest.param(f"https://{_PRODUCT_NAME}-team.feishu.cn/x", [f"{_PRODUCT_NAME}-team.feishu.cn"], id="vendor-tenant"),
    pytest.param(f"https://{_PRODUCT_NAME}agent.com", [f"{_PRODUCT_NAME}agent.com"], id="other-top-level-domain"),
    pytest.param(
        f"https://x.{_OFFICIAL_DOMAIN}.other.com/a",
        [f"x.{_OFFICIAL_DOMAIN}.other.com"],
        id="official-name-inside-another-host",
    ),
    pytest.param(f"sales@{_PRODUCT_NAME}.sh", [f"{_PRODUCT_NAME}.sh"], id="email-on-an-unowned-domain"),
    pytest.param(f"HTTPS://{_PRODUCT_NAME.upper()}-X.COM", [f"{_PRODUCT_NAME}-x.com"], id="upper-case"),
    pytest.param(f"https://{_PRODUCT_NAME}.example.com/a", [], id="reserved-example-com"),
    pytest.param(f"https://x.{_PRODUCT_NAME}.example/a", [], id="reserved-example"),
    pytest.param(f"git@{_PRODUCT_NAME}.local", [], id="reserved-local"),
    pytest.param(f"https://example.com/{_PRODUCT_NAME}", [], id="name-only-in-the-path"),
    pytest.param("https://github.com/Pursue-LLL/myrm-agent", [], id="repository-name"),
    pytest.param(f"npm i @{_PRODUCT_NAME}/pkg", [], id="package-scope-without-a-host"),
    pytest.param(
        f"a https://{_PRODUCT_NAME}-a.com and b https://{_PRODUCT_NAME}-b.org",
        [f"{_PRODUCT_NAME}-a.com", f"{_PRODUCT_NAME}-b.org"],
        id="several-hosts-in-one-line",
    ),
]


def _git_grep(pattern: str, args: list[str], cwd: Path) -> list[str]:
    """Return ``path:line:text`` rows matching ``pattern``, ignoring case (git grep status 1 means none)."""
    result = subprocess.run(
        ["git", "grep", "-I", "-n", "-i", "-E", "-e", pattern, *args],
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(f"git grep failed with status {result.returncode}: {result.stderr.strip()}")
    return result.stdout.splitlines()


def _fail_on_hits(hits: list[str], reason: str) -> None:
    if not hits:
        return
    detail = "\n".join(row[:200] for row in hits[:_MAX_REPORTED_HITS])
    if len(hits) > _MAX_REPORTED_HITS:
        detail += f"\n... and {len(hits) - _MAX_REPORTED_HITS} more"
    pytest.fail(f"{reason}\n{detail}")


def _matches_sample(pattern: str, line: str, tmp_path: Path) -> bool:
    sample = tmp_path / "sample.txt"
    sample.write_text(line + "\n", encoding="utf-8")
    return bool(_git_grep(pattern, ["--no-index", "--", sample.name], cwd=tmp_path))


def _non_official_hosts(text: str) -> list[str]:
    """Hosts in ``text`` that carry the product name but are neither the official domain nor a reserved name."""
    hosts = (match.group(1).lower() for match in _HOST_GRAMMAR.finditer(text))
    return [
        host
        for host in hosts
        if _PRODUCT_NAME in host
        and host != _OFFICIAL_DOMAIN
        and not host.endswith(f".{_OFFICIAL_DOMAIN}")
        and not host.endswith(_RESERVED_SUFFIXES)
    ]


@pytest.mark.parametrize(("line", "expected"), _LEGACY_CASES)
def test_legacy_pattern_matches_exactly_the_retired_domain_shapes(line: str, expected: bool, tmp_path: Path) -> None:
    assert _matches_sample(_LEGACY_PATTERN, line, tmp_path) is expected


@pytest.mark.parametrize(("line", "expected"), _ANY_BRAND_CASES)
def test_brand_domain_pattern_matches_legacy_and_official_domains(line: str, expected: bool, tmp_path: Path) -> None:
    assert _matches_sample(_ANY_BRAND_DOMAIN_PATTERN, line, tmp_path) is expected


@pytest.mark.parametrize(("line", "expected"), _HOST_CASES)
def test_host_rule_flags_exactly_the_non_official_product_hosts(line: str, expected: list[str]) -> None:
    assert _non_official_hosts(line) == expected


@pytest.mark.parametrize("line", [case.values[0] for case in _HOST_CASES if case.values[1]])
def test_host_prefilter_keeps_every_line_the_host_rule_flags(line: str, tmp_path: Path) -> None:
    assert _matches_sample(_HOST_PREFILTER, line, tmp_path)


def test_tracked_text_files_have_no_retired_brand_domain() -> None:
    _fail_on_hits(
        _git_grep(_LEGACY_PATTERN, ["--", "."], cwd=_REPO_ROOT),
        "Tracked files contain a retired brand domain. Use the official domain from the brand constants "
        "(server: app.core.brand, frontend: src/lib/constants/brand.ts), or a reserved example domain in tests and samples.",
    )


def test_harness_sources_name_no_brand_domain() -> None:
    _fail_on_hits(
        _git_grep(_ANY_BRAND_DOMAIN_PATTERN, ["--", _HARNESS_SOURCES], cwd=_REPO_ROOT),
        "The harness is published for third parties and knows no product brand: it must not name a brand domain, "
        "official or retired. The host application registers its own identity.",
    )


def test_hosts_carrying_the_product_name_are_official_or_reserved() -> None:
    rows = _git_grep(_HOST_PREFILTER, ["--", "."], cwd=_REPO_ROOT)
    offenders = [row for row in rows if _non_official_hosts(row.split(":", 2)[-1])]
    _fail_on_hits(
        offenders,
        "A URL or email address names a host that carries the product name but is neither the official domain nor a "
        "reserved example name (.example, .example.com, .local). Use the brand constants, or a reserved name in samples.",
    )
