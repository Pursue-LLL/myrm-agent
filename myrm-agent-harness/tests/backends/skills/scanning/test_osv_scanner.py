"""Tests for osv_scanner.py: the batch endpoint answers with advisory ids only, so severity and text come from the
full records fetched afterwards."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import cast
from unittest.mock import patch
from urllib.parse import unquote

import httpx
import pytest

from myrm_agent_harness.backends.skills.scanning import osv_scanner
from myrm_agent_harness.backends.skills.scanning.dependency_extractor import DeclaredDependency
from myrm_agent_harness.backends.skills.scanning.osv_scanner import parse_osv_severity, query_osv_batch
from myrm_agent_harness.backends.skills.scanning.scanner import ScanSeverity
from myrm_agent_harness.backends.skills.scanning.security_advisories import AdvisoryFinding
from myrm_agent_harness.backends.skills.scanning.vuln_cache import VulnScanCache

_CREATE_CLIENT = "myrm_agent_harness.backends.skills.scanning.osv_scanner.create_httpx_client"

_CRITICAL_VECTOR = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"  # 9.8
_HIGH_VECTOR = "CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:H/A:N"  # 7.4
_MEDIUM_VECTOR = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N"  # 5.3
_LOW_VECTOR = "CVSS:3.1/AV:P/AC:H/PR:H/UI:R/S:U/C:L/I:N/A:N"  # 1.6
_V4_VECTOR = "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N"

_GHSA_RECORD: dict[str, object] = {
    "id": "GHSA-aaaa-bbbb-cccc",
    "summary": "Prototype pollution in left-pad",
    "details": "Long description of the prototype pollution.",
    "database_specific": {"severity": "HIGH"},
}
_PYSEC_RECORD: dict[str, object] = {
    "id": "PYSEC-2026-1",
    "details": "Advisory without a summary line.",
    "severity": [{"type": "CVSS_V3", "score": _HIGH_VECTOR}],
}


class _FakeResponse:
    def __init__(self, payload: object, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://api.osv.dev")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("error", request=request, response=response)

    def json(self) -> object:
        return self._payload


class _FakeOsvClient:
    """Answers like OSV.dev: the batch endpoint returns advisory ids only, /vulns/<id> the full record."""

    def __init__(self, advisories: Mapping[str, Sequence[str]], records: Mapping[str, dict[str, object]]) -> None:
        self._advisories = advisories  # "name@version" (or "name@*" for an unpinned query) -> advisory ids
        self._records = records
        self.queries_per_batch: list[list[dict[str, object]]] = []
        self.record_requests: list[str] = []
        self.post_errors: list[Exception] = []  # raised by the next batch POSTs, one per call
        self.get_statuses: list[int] = []  # answered by the next record GETs, one per call

    async def __aenter__(self) -> _FakeOsvClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def post(self, url: str, *, json: dict[str, list[dict[str, object]]]) -> _FakeResponse:
        queries = json["queries"]
        self.queries_per_batch.append(queries)
        if self.post_errors:
            raise self.post_errors.pop(0)
        results = []
        for query in queries:
            package = cast(dict[str, str], query["package"])
            key = f"{package['name']}@{query.get('version', '*')}"
            vulns = [
                {"id": advisory_id, "modified": "2026-01-01T00:00:00Z"} for advisory_id in self._advisories.get(key, ())
            ]
            results.append({"vulns": vulns})
        return _FakeResponse({"results": results})

    async def get(self, url: str) -> _FakeResponse:
        advisory_id = unquote(url.rsplit("/", 1)[1])
        self.record_requests.append(advisory_id)
        if self.get_statuses:
            return _FakeResponse({}, self.get_statuses.pop(0))
        if advisory_id not in self._records:
            raise ConnectionError("record endpoint unreachable")
        return _FakeResponse(self._records[advisory_id])


def _dep(name: str, version: str = "1.0.0", ecosystem: str = "npm", file_path: str = "bun.lock") -> DeclaredDependency:
    return DeclaredDependency(name=name, version_spec=version, ecosystem=ecosystem, file_path=file_path)


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        ({"id": "MAL-2024-001"}, ScanSeverity.CRITICAL),
        ({"id": "GHSA-1", "database_specific": {"severity": "CRITICAL"}}, ScanSeverity.CRITICAL),
        ({"id": "GHSA-1", "database_specific": {"severity": "HIGH"}}, ScanSeverity.HIGH),
        ({"id": "GHSA-1", "database_specific": {"severity": "MODERATE"}}, ScanSeverity.MEDIUM),
        ({"id": "GHSA-1", "database_specific": {"severity": "LOW"}}, ScanSeverity.LOW),
        ({"id": "PYSEC-1", "severity": [{"type": "CVSS_V3", "score": _CRITICAL_VECTOR}]}, ScanSeverity.CRITICAL),
        ({"id": "PYSEC-1", "severity": [{"type": "CVSS_V3", "score": _HIGH_VECTOR}]}, ScanSeverity.HIGH),
        ({"id": "PYSEC-1", "severity": [{"type": "CVSS_V3", "score": _MEDIUM_VECTOR}]}, ScanSeverity.MEDIUM),
        ({"id": "PYSEC-1", "severity": [{"type": "CVSS_V3", "score": _LOW_VECTOR}]}, ScanSeverity.LOW),
        # The database label wins over a vector, and an unsupported v4 vector is skipped in favour of a v3 one.
        (
            {"id": "GHSA-1", "database_specific": {"severity": "LOW"}, "severity": [{"score": _CRITICAL_VECTOR}]},
            ScanSeverity.LOW,
        ),
        (
            {"id": "PYSEC-1", "severity": [{"type": "CVSS_V4", "score": _V4_VECTOR}, {"score": _CRITICAL_VECTOR}]},
            ScanSeverity.CRITICAL,
        ),
        # Nothing usable to rate with: MEDIUM, which is also all an id-only batch entry can ever resolve to.
        ({"id": "PYSEC-1", "severity": [{"type": "CVSS_V4", "score": _V4_VECTOR}]}, ScanSeverity.MEDIUM),
        ({"id": "PYSEC-1"}, ScanSeverity.MEDIUM),
        ({"id": "GHSA-1", "modified": "2026-01-01T00:00:00Z"}, ScanSeverity.MEDIUM),
    ],
)
def test_parse_osv_severity(record: dict[str, object], expected: ScanSeverity) -> None:
    assert parse_osv_severity(record) == expected


async def test_query_osv_batch_takes_severity_and_text_from_the_full_record() -> None:
    client = _FakeOsvClient(
        {"left-pad@1.0.0": ["GHSA-aaaa-bbbb-cccc"], "pyyaml@5.0.0": ["PYSEC-2026-1"]},
        {"GHSA-aaaa-bbbb-cccc": _GHSA_RECORD, "PYSEC-2026-1": _PYSEC_RECORD},
    )
    deps = [_dep("left-pad"), _dep("pyyaml", "5.0.0", "PyPI", "uv.lock"), _dep("clean")]

    with patch(_CREATE_CLIENT, return_value=client):
        findings = await query_osv_batch(deps, cache=VulnScanCache())

    by_id = {finding.advisory_id: finding for finding in findings}
    assert set(by_id) == {"GHSA-aaaa-bbbb-cccc", "PYSEC-2026-1"}
    ghsa = by_id["GHSA-aaaa-bbbb-cccc"]
    assert ghsa == AdvisoryFinding(
        advisory_id="GHSA-aaaa-bbbb-cccc",
        package_name="left-pad",
        ecosystem="npm",
        severity=ScanSeverity.HIGH,
        title="Prototype pollution in left-pad",
        description="Long description of the prototype pollution.",
        matched_version="1.0.0",
        file_path="bun.lock",
        source="osv_api",
    )
    pysec = by_id["PYSEC-2026-1"]
    assert (pysec.severity, pysec.title, pysec.file_path) == (
        ScanSeverity.HIGH,
        "Advisory without a summary line.",
        "uv.lock",
    )


async def test_query_osv_batch_fetches_each_advisory_record_once() -> None:
    client = _FakeOsvClient(
        {"left-pad@1.0.0": ["GHSA-aaaa-bbbb-cccc"], "left-pad@1.0.1": ["GHSA-aaaa-bbbb-cccc"]},
        {"GHSA-aaaa-bbbb-cccc": _GHSA_RECORD},
    )

    with patch(_CREATE_CLIENT, return_value=client):
        findings = await query_osv_batch([_dep("left-pad"), _dep("left-pad", "1.0.1")], cache=VulnScanCache())

    assert len(findings) == 2
    assert client.record_requests == ["GHSA-aaaa-bbbb-cccc"]


async def test_query_osv_batch_splits_dependencies_into_batches_of_100() -> None:
    client = _FakeOsvClient({}, {})

    with patch(_CREATE_CLIENT, return_value=client):
        findings = await query_osv_batch([_dep(f"pkg-{i}") for i in range(250)], cache=VulnScanCache())

    assert findings == []
    assert sorted(len(batch) for batch in client.queries_per_batch) == [50, 100, 100]


async def test_query_osv_batch_pins_the_version_only_for_exact_specs() -> None:
    client = _FakeOsvClient({}, {})
    deps = [_dep("ranged", "^1.0.0"), _dep("pinned", "==2.0.0", "PyPI"), _dep("exact", "3.0.0")]

    with patch(_CREATE_CLIENT, return_value=client):
        await query_osv_batch(deps, cache=VulnScanCache())

    assert [query.get("version") for query in client.queries_per_batch[0]] == [None, "2.0.0", "3.0.0"]


@pytest.mark.parametrize(
    ("spec", "pinned"),
    [
        ("312", "312"),  # pywin32 in uv.lock
        ("20260107", "20260107"),  # pdfminer-six in uv.lock
        ("1.2.3", "1.2.3"),
        ("==2.0.0", "2.0.0"),
        (">=1.0", None),
        ("^1.2.3", None),
        ("*", None),
        ("latest", None),
        ("", None),
    ],
)
async def test_query_osv_batch_pins_a_bare_version_even_without_a_dot(spec: str, pinned: str | None) -> None:
    client = _FakeOsvClient({}, {})

    with patch(_CREATE_CLIENT, return_value=client):
        await query_osv_batch([_dep("pywin32", spec, "PyPI", "uv.lock")], cache=VulnScanCache())

    assert [query.get("version") for query in client.queries_per_batch[0]] == [pinned]


async def test_query_osv_batch_does_not_report_advisories_fixed_before_a_dotless_locked_version() -> None:
    # OSV answers a version query with the advisories that affect that version: pywin32 312 is past the fix (301),
    # whereas a query without the version would return every advisory ever filed for the package.
    client = _FakeOsvClient({"pywin32@*": ["GHSA-aaaa-bbbb-cccc"]}, {"GHSA-aaaa-bbbb-cccc": _GHSA_RECORD})

    with patch(_CREATE_CLIENT, return_value=client):
        findings = await query_osv_batch([_dep("pywin32", "312", "PyPI", "uv.lock")], cache=VulnScanCache())

    assert findings == []


async def test_query_osv_batch_defaults_to_medium_and_skips_the_cache_when_a_record_is_unavailable(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = _FakeOsvClient({"left-pad@1.0.0": ["GHSA-aaaa-bbbb-cccc"]}, {})
    cache = VulnScanCache()

    with patch(_CREATE_CLIENT, return_value=client), caplog.at_level(logging.WARNING):
        findings = await query_osv_batch([_dep("left-pad")], cache=cache)

    assert [(f.advisory_id, f.severity, f.title) for f in findings] == [
        ("GHSA-aaaa-bbbb-cccc", ScanSeverity.MEDIUM, "Vulnerability advisory")
    ]
    assert cache.get("npm", "left-pad", "1.0.0") is None
    assert "OSV records unavailable for 1 advisories" in caplog.text


async def test_query_osv_batch_keeps_findings_of_unpinned_dependencies_informational() -> None:
    # Without a pinned version OSV returns every advisory ever filed for the package, so none of them is known to
    # affect the version that gets installed; malware still names the whole package.
    client = _FakeOsvClient(
        {
            "left-pad@*": ["GHSA-aaaa-bbbb-cccc"],
            "tiny@*": ["GHSA-low"],
            "evil@*": ["MAL-2026-1"],
            "left-pad@1.0.0": ["GHSA-aaaa-bbbb-cccc"],
        },
        {
            "GHSA-aaaa-bbbb-cccc": _GHSA_RECORD,
            "GHSA-low": {"id": "GHSA-low", "database_specific": {"severity": "LOW"}},
        },
    )
    deps = [_dep("left-pad", "^1.0.0"), _dep("tiny", ">=2"), _dep("evil", "*")]

    with patch(_CREATE_CLIENT, return_value=client):
        unpinned = await query_osv_batch(deps, cache=VulnScanCache())
        pinned = await query_osv_batch([_dep("left-pad")], cache=VulnScanCache())

    assert {f.package_name: f.severity for f in unpinned} == {
        "left-pad": ScanSeverity.MEDIUM,
        "tiny": ScanSeverity.LOW,
        "evil": ScanSeverity.CRITICAL,
    }
    assert [f.severity for f in pinned] == [ScanSeverity.HIGH]


async def test_query_osv_batch_without_severity_resolution_rates_by_advisory_id_alone(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = _FakeOsvClient(
        {"left-pad@1.0.0": ["GHSA-aaaa-bbbb-cccc"], "evil@1.0.0": ["MAL-2026-1"]},
        {"GHSA-aaaa-bbbb-cccc": _GHSA_RECORD},
    )
    cache = VulnScanCache()
    deps = [_dep("left-pad"), _dep("evil"), _dep("clean")]

    with patch(_CREATE_CLIENT, return_value=client), caplog.at_level(logging.WARNING):
        findings = await query_osv_batch(deps, cache=cache, resolve_severity=False)

    assert client.record_requests == []
    assert {f.package_name: f.severity for f in findings} == {
        "left-pad": ScanSeverity.MEDIUM,
        "evil": ScanSeverity.CRITICAL,
    }
    assert caplog.text == ""
    # Only the verdict "no advisory" is final; an unresolved finding must not be served later as if it were resolved.
    assert cache.get("npm", "clean", "1.0.0") == []
    assert cache.get("npm", "left-pad", "1.0.0") is None
    with patch(_CREATE_CLIENT, return_value=client):
        resolved = await query_osv_batch(deps, cache=cache)
    assert {f.package_name: f.severity for f in resolved} == {
        "left-pad": ScanSeverity.HIGH,
        "evil": ScanSeverity.CRITICAL,
    }


async def test_query_osv_batch_retries_transient_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(osv_scanner, "_RETRY_DELAYS_SECONDS", (0.0, 0.0))
    client = _FakeOsvClient({"left-pad@1.0.0": ["GHSA-aaaa-bbbb-cccc"]}, {"GHSA-aaaa-bbbb-cccc": _GHSA_RECORD})
    client.post_errors = [httpx.ConnectTimeout("connect timed out"), httpx.ReadTimeout("read timed out")]
    client.get_statuses = [503]

    with patch(_CREATE_CLIENT, return_value=client):
        findings = await query_osv_batch([_dep("left-pad")], cache=VulnScanCache())

    assert [(f.advisory_id, f.severity) for f in findings] == [("GHSA-aaaa-bbbb-cccc", ScanSeverity.HIGH)]
    assert len(client.queries_per_batch) == 3  # two failed attempts, then the answer
    assert client.record_requests == ["GHSA-aaaa-bbbb-cccc"] * 2  # a 503, then the record


async def test_query_osv_batch_gives_up_after_three_attempts(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(osv_scanner, "_RETRY_DELAYS_SECONDS", (0.0, 0.0))
    client = _FakeOsvClient({}, {})
    client.post_errors = [httpx.ConnectTimeout("connect timed out")] * 5
    cache = VulnScanCache()

    with patch(_CREATE_CLIENT, return_value=client), caplog.at_level(logging.WARNING):
        findings = await query_osv_batch([_dep("left-pad")], cache=cache)

    assert findings == []
    assert len(client.queries_per_batch) == 3
    assert cache.get("npm", "left-pad", "1.0.0") is None
    assert "OSV could not be queried for 1 of 1 dependencies" in caplog.text


async def test_query_osv_batch_does_not_retry_client_errors() -> None:
    client = _FakeOsvClient({"left-pad@1.0.0": ["GHSA-aaaa-bbbb-cccc"]}, {})
    client.get_statuses = [404]

    with patch(_CREATE_CLIENT, return_value=client):
        findings = await query_osv_batch([_dep("left-pad")], cache=VulnScanCache())

    assert client.record_requests == ["GHSA-aaaa-bbbb-cccc"]
    assert [f.severity for f in findings] == [ScanSeverity.MEDIUM]


async def test_query_osv_batch_rates_malware_critical_without_its_record() -> None:
    client = _FakeOsvClient({"evil@1.0.0": ["MAL-2026-1"]}, {})

    with patch(_CREATE_CLIENT, return_value=client):
        findings = await query_osv_batch([_dep("evil")], cache=VulnScanCache())

    assert [(f.advisory_id, f.severity) for f in findings] == [("MAL-2026-1", ScanSeverity.CRITICAL)]


async def test_query_osv_batch_caches_resolved_findings_per_package_version() -> None:
    client = _FakeOsvClient({"left-pad@1.0.0": ["GHSA-aaaa-bbbb-cccc"]}, {"GHSA-aaaa-bbbb-cccc": _GHSA_RECORD})
    cache = VulnScanCache()
    with patch(_CREATE_CLIENT, return_value=client):
        await query_osv_batch([_dep("left-pad", file_path="a/bun.lock")], cache=cache)

    with patch(_CREATE_CLIENT, side_effect=AssertionError("a cached dependency must not reach the network")):
        findings = await query_osv_batch([_dep("left-pad", file_path="b/bun.lock")], cache=cache)

    assert [(f.advisory_id, f.severity, f.file_path) for f in findings] == [
        ("GHSA-aaaa-bbbb-cccc", ScanSeverity.HIGH, "b/bun.lock")
    ]


async def test_query_osv_batch_keeps_the_other_batches_when_one_fails() -> None:
    advisories = {"pkg-10@1.0.0": ["GHSA-aaaa-bbbb-cccc"], "pkg-120@1.0.0": ["GHSA-aaaa-bbbb-cccc"]}
    client = _FakeOsvClient(advisories, {"GHSA-aaaa-bbbb-cccc": _GHSA_RECORD})
    client.post_errors = [ValueError("malformed batch answer")]  # the first batch (pkg-0 .. pkg-99) is lost
    cache = VulnScanCache()

    with patch(_CREATE_CLIENT, return_value=client):
        findings = await query_osv_batch([_dep(f"pkg-{i}") for i in range(150)], cache=cache)

    assert [f.package_name for f in findings] == ["pkg-120"]
    assert cache.get("npm", "pkg-10", "1.0.0") is None
    assert cache.get("npm", "pkg-120", "1.0.0") is not None


async def test_query_osv_batch_warns_and_returns_cached_findings_when_the_client_cannot_be_used(
    caplog: pytest.LogCaptureFixture,
) -> None:
    cache = VulnScanCache()
    cached = AdvisoryFinding(
        advisory_id="GHSA-cached",
        package_name="cached-pkg",
        ecosystem="npm",
        severity=ScanSeverity.HIGH,
        title="Cached",
        description="Detail",
        matched_version="1.0.0",
    )
    cache.set("npm", "cached-pkg", "1.0.0", [cached])

    with patch(_CREATE_CLIENT, side_effect=ConnectionError("offline")), caplog.at_level(logging.WARNING):
        findings = await query_osv_batch([_dep("cached-pkg"), _dep("uncached-pkg")], cache=cache)

    assert [f.advisory_id for f in findings] == ["GHSA-cached"]
    # A scan that silently skipped every uncached dependency would look like a clean result.
    assert "OSV client failed (offline)" in caplog.text


async def test_query_osv_batch_without_dependencies_never_touches_the_network() -> None:
    with patch(_CREATE_CLIENT, side_effect=AssertionError("no dependency, no request")):
        assert await query_osv_batch([], cache=VulnScanCache()) == []
