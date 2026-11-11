"""Tests for security_advisories.py and vuln_cache.py."""

from pathlib import Path

from myrm_agent_harness.backends.skills.scanning.dependency_extractor import DeclaredDependency
from myrm_agent_harness.backends.skills.scanning.scanner import ScanSeverity
from myrm_agent_harness.backends.skills.scanning.security_advisories import (
    AdvisoryFinding,
    get_known_advisories_catalog,
    match_known_advisories,
)
from myrm_agent_harness.backends.skills.scanning.vuln_cache import (
    VulnScanCache,
    get_vuln_cache,
)


def test_match_known_advisories_fuzzy_and_wildcard() -> None:
    # Wildcard advisory
    deps = [
        DeclaredDependency(name="flatmap-stream", version_spec="0.1.1", ecosystem="npm"),
        DeclaredDependency(name="noblesse", version_spec="*", ecosystem="PyPI"),
        DeclaredDependency(name="unknown-pkg", version_spec="1.0.0", ecosystem="npm"),
    ]
    findings = match_known_advisories(deps)
    assert len(findings) == 2
    ids = {f.advisory_id for f in findings}
    assert "MAL-2018-002" in ids
    assert "MAL-2024-001" in ids


def test_known_advisories_catalog_and_match() -> None:
    catalog = get_known_advisories_catalog()
    assert len(catalog) >= 10

    # 1. Match compromised event-stream
    deps = [
        DeclaredDependency(
            name="event-stream",
            version_spec="3.3.6",
            ecosystem="npm",
        ),
        DeclaredDependency(
            name="safe-package",
            version_spec="1.0.0",
            ecosystem="npm",
        ),
    ]
    findings = match_known_advisories(deps)
    assert len(findings) == 1
    assert findings[0].advisory_id == "MAL-2018-001"
    assert findings[0].severity == ScanSeverity.CRITICAL

    # 2. Match hijacked ctx package on PyPI
    pypi_deps = [
        DeclaredDependency(
            name="ctx",
            version_spec="==0.1.2",
            ecosystem="PyPI",
        )
    ]
    pypi_findings = match_known_advisories(pypi_deps)
    assert len(pypi_findings) == 1
    assert pypi_findings[0].advisory_id == "MAL-2022-004"


def test_vuln_cache_invalid_json(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("not json", encoding="utf-8")
    cache = VulnScanCache()
    assert cache.load_from_disk(bad_file) is False

    dict_file = tmp_path / "dict.json"
    dict_file.write_text("{}", encoding="utf-8")
    assert cache.load_from_disk(dict_file) is False


def test_vuln_cache_lifecycle(tmp_path: Path) -> None:
    cache = VulnScanCache(default_ttl_seconds=10.0)
    assert cache.get("npm", "pkg-a", "1.0.0") is None

    finding = AdvisoryFinding(
        advisory_id="TEST-001",
        package_name="pkg-a",
        ecosystem="npm",
        severity=ScanSeverity.HIGH,
        title="Test vuln",
        description="Detail",
        matched_version="1.0.0",
    )
    cache.set("npm", "pkg-a", "1.0.0", [finding])

    hit = cache.get("npm", "pkg-a", "1.0.0")
    assert hit is not None
    assert len(hit) == 1
    assert hit[0].advisory_id == "TEST-001"

    # Disk persist & load
    cache_file = tmp_path / "vuln_cache.json"
    assert cache.save_to_disk(cache_file) is True
    assert cache_file.exists()

    new_cache = VulnScanCache()
    assert new_cache.load_from_disk(cache_file) is True
    new_hit = new_cache.get("npm", "pkg-a", "1.0.0")
    assert new_hit is not None
    assert len(new_hit) == 1

    # Prune and clear
    assert cache.prune_expired() == 0
    cache.clear()
    assert cache.get("npm", "pkg-a", "1.0.0") is None


def test_is_version_affected_branches() -> None:
    from myrm_agent_harness.backends.skills.scanning.security_advisories import _is_version_affected

    assert _is_version_affected("1.0.0", []) is False
    assert _is_version_affected("1.0.0", ("*",)) is True
    assert _is_version_affected("", ("1.0.0",)) is True
    assert _is_version_affected("1.0.0.1", ("1.0.0",)) is True


def test_advisory_finding_fields() -> None:
    f = AdvisoryFinding(
        advisory_id="TEST-1",
        package_name="test-pkg",
        ecosystem="npm",
        severity=ScanSeverity.CRITICAL,
        title="Title",
        description="Desc",
        matched_version="1.0.0",
    )
    assert f.advisory_id == "TEST-1"
    assert f.is_acked is False


def test_vuln_cache_default_singleton() -> None:
    c = get_vuln_cache()
    assert c is not None
    assert isinstance(c, VulnScanCache)
