"""OSV.dev Batch Vulnerability and Supply Chain Scanner.

Provides asynchronous querying of OSV.dev (Open Source Vulnerabilities) API. The batch endpoint answers with advisory
ids only, so every distinct id is then resolved to its full record, which carries the severity and the summary.
Results are cached per package version with a TTL and the scan degrades gracefully when offline.

[INPUT]
- DeclaredDependency (from dependency_extractor)
- VulnScanCache (from vuln_cache)
- ScanSeverity (from scanner)
- AdvisoryFinding (from security_advisories)
- cvss_v3_base_score (from cvss)

[OUTPUT]
- query_osv_batch: batch scan declared dependencies against OSV.dev
- parse_osv_severity: map a full OSV record (ID prefix / database label / CVSS v3 vector) to ScanSeverity

[POS]
Online vulnerability intelligence provider for skill supply chain security.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import replace
from urllib.parse import quote

import httpx

from myrm_agent_harness.backends.skills.scanning.cvss import cvss_v3_base_score
from myrm_agent_harness.backends.skills.scanning.dependency_extractor import DeclaredDependency
from myrm_agent_harness.backends.skills.scanning.scanner import ScanSeverity
from myrm_agent_harness.backends.skills.scanning.security_advisories import AdvisoryFinding
from myrm_agent_harness.backends.skills.scanning.vuln_cache import VulnScanCache, get_vuln_cache
from myrm_agent_harness.infra.tls_compat import create_httpx_client

logger = logging.getLogger(__name__)

_OSV_QUERYBATCH_URL = "https://api.osv.dev/v1/querybatch"
_OSV_VULN_URL = "https://api.osv.dev/v1/vulns/"
_OSV_TIMEOUT_SECONDS = 5.0
_MAX_BATCH_SIZE = 100
_MAX_CONCURRENT_REQUESTS = 8
# One retry per delay, so a request is attempted at most three times: a connection that times out or a throttled
# answer is routine when many requests are in flight, and must not silently turn into a missing finding.
_RETRY_DELAYS_SECONDS = (0.5, 1.0)
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
_FALLBACK_SUMMARY = "Vulnerability advisory"
_MALWARE_ID_PREFIX = "MAL-"

# Order matters: a label naming several levels resolves to the most severe one.
_DATABASE_SEVERITY_LABELS: tuple[tuple[str, ScanSeverity], ...] = (
    ("CRITICAL", ScanSeverity.CRITICAL),
    ("HIGH", ScanSeverity.HIGH),
    ("MODERATE", ScanSeverity.MEDIUM),
    ("MEDIUM", ScanSeverity.MEDIUM),
    ("LOW", ScanSeverity.LOW),
)


def _severity_from_cvss_score(score: float) -> ScanSeverity:
    if score >= 9.0:
        return ScanSeverity.CRITICAL
    if score >= 7.0:
        return ScanSeverity.HIGH
    if score >= 4.0:
        return ScanSeverity.MEDIUM
    return ScanSeverity.LOW


def _is_malware_advisory(advisory_id: str) -> bool:
    """Whether the advisory reports a malicious package (OSV `MAL-*` ids) rather than a vulnerable one."""
    return advisory_id.upper().startswith(_MALWARE_ID_PREFIX)


def parse_osv_severity(vuln_data: Mapping[str, object]) -> ScanSeverity:
    """Map a full OSV record to ScanSeverity.

    Malware ids are CRITICAL. Otherwise the database-assigned label wins (GitHub advisories), then the CVSS v3 base
    score computed from the record's vector (PYSEC advisories). A record with neither, including one rated only with
    a CVSS v4 vector, is MEDIUM. A batch-query entry (id only) therefore never rates above MEDIUM.
    """
    if _is_malware_advisory(str(vuln_data.get("id", ""))):
        return ScanSeverity.CRITICAL

    database_specific = vuln_data.get("database_specific")
    if isinstance(database_specific, dict):
        label = str(database_specific.get("severity", "")).upper()
        for needle, severity in _DATABASE_SEVERITY_LABELS:
            if needle in label:
                return severity

    ratings = vuln_data.get("severity")
    if isinstance(ratings, list):
        for rating in ratings:
            if isinstance(rating, dict):
                score = cvss_v3_base_score(str(rating.get("score", "")))
                if score is not None:
                    return _severity_from_cvss_score(score)

    return ScanSeverity.MEDIUM


def _normalize_exact_version(version_spec: str) -> str | None:
    """Extract the exact version a spec pins: ``==1.2.3``, or a bare version such as ``1.2.3``, ``312`` or ``20260107``.

    A lockfile entry is a bare version and not every project's versions contain a dot, so the dot is optional.
    """
    spec = version_spec.strip()
    if not spec:
        return None
    match = re.match(r"^==?\s*([0-9A-Za-z._-]+)$", spec)
    if match:
        return match.group(1).strip()
    if re.match(r"^[0-9]+(?:\.[0-9A-Za-z._-]+)*$", spec):
        return spec
    return None


def _build_query(dep: DeclaredDependency) -> dict[str, object]:
    query: dict[str, object] = {"package": {"name": dep.name, "ecosystem": dep.ecosystem}}
    exact_version = _normalize_exact_version(dep.version_spec)
    if exact_version:
        query["version"] = exact_version
    return query


async def _send_with_retries(send: Callable[[], Awaitable[httpx.Response]]) -> httpx.Response:
    """Send a request, retrying transport failures and throttled or failing answers; the last attempt may raise."""
    for delay in _RETRY_DELAYS_SECONDS:
        try:
            response = await send()
        except httpx.TransportError:
            pass
        else:
            if response.status_code not in _RETRYABLE_STATUS_CODES:
                response.raise_for_status()
                return response
        await asyncio.sleep(delay)
    response = await send()
    response.raise_for_status()
    return response


def _advisory_ids(result: object) -> list[str]:
    vulns = result.get("vulns") if isinstance(result, dict) else None
    if not isinstance(vulns, list):
        return []
    return [vuln["id"] for vuln in vulns if isinstance(vuln, dict) and isinstance(vuln.get("id"), str)]


async def _query_advisory_ids(
    client: httpx.AsyncClient,
    dependencies: Sequence[DeclaredDependency],
    semaphore: asyncio.Semaphore,
) -> list[list[str] | None]:
    """Return the advisory ids affecting each dependency, or None for a dependency whose batch failed."""

    async def query(batch: Sequence[DeclaredDependency]) -> list[list[str] | None]:
        async with semaphore:
            try:
                payload = {"queries": [_build_query(d) for d in batch]}
                response = await _send_with_retries(lambda: client.post(_OSV_QUERYBATCH_URL, json=payload))
                results = response.json().get("results")
            except Exception as exc:  # Fail open: an unreachable OSV must not break the caller's scan.
                logger.debug("OSV batch query failed or timed out: %s", exc)
                return [None] * len(batch)
        if not isinstance(results, list):
            return [None] * len(batch)
        ids: list[list[str] | None] = [_advisory_ids(result) for result in results[: len(batch)]]
        return ids + [None] * (len(batch) - len(ids))

    batches = [dependencies[i : i + _MAX_BATCH_SIZE] for i in range(0, len(dependencies), _MAX_BATCH_SIZE)]
    per_batch = await asyncio.gather(*(query(batch) for batch in batches))
    advisory_ids = [ids for batch_ids in per_batch for ids in batch_ids]
    unchecked = sum(ids is None for ids in advisory_ids)
    if unchecked:
        logger.warning(
            "OSV could not be queried for %d of %d dependencies; they were not checked.", unchecked, len(dependencies)
        )
    return advisory_ids


async def _fetch_records(
    client: httpx.AsyncClient,
    advisory_ids: set[str],
    semaphore: asyncio.Semaphore,
) -> dict[str, dict[str, object]]:
    """Resolve advisory ids to their full OSV records; an id whose record could not be fetched is left out."""

    async def fetch(advisory_id: str) -> tuple[str, dict[str, object] | None]:
        async with semaphore:
            try:
                url = f"{_OSV_VULN_URL}{quote(advisory_id, safe='')}"
                response = await _send_with_retries(lambda: client.get(url))
                record = response.json()
            except Exception as exc:  # Fail open: the finding keeps the default severity.
                logger.debug("OSV record fetch failed for %s: %s", advisory_id, exc)
                return advisory_id, None
        return advisory_id, record if isinstance(record, dict) else None

    fetched = await asyncio.gather(*(fetch(advisory_id) for advisory_id in sorted(advisory_ids)))
    return {advisory_id: record for advisory_id, record in fetched if record is not None}


def _build_finding(dep: DeclaredDependency, advisory_id: str, record: Mapping[str, object] | None) -> AdvisoryFinding:
    # Without a record the id alone still identifies malware (MAL-*); everything else keeps the default severity.
    full_record: Mapping[str, object] = record if record is not None else {"id": advisory_id}
    summary = str(full_record.get("summary") or full_record.get("details") or _FALLBACK_SUMMARY)
    severity = parse_osv_severity(full_record)
    if (
        severity > ScanSeverity.MEDIUM
        and not _is_malware_advisory(advisory_id)
        and _normalize_exact_version(dep.version_spec) is None
    ):
        # OSV answers an unpinned dependency with every advisory ever filed for the package, so whether the version
        # that actually gets installed is affected is unknown: such a finding stays informational.
        severity = ScanSeverity.MEDIUM
    return AdvisoryFinding(
        advisory_id=advisory_id,
        package_name=dep.name,
        ecosystem=dep.ecosystem,
        severity=severity,
        title=summary[:200],
        description=str(full_record.get("details") or summary)[:500],
        matched_version=dep.version_spec or "*",
        file_path=dep.file_path,
        is_acked=False,
        source="osv_api",
    )


async def query_osv_batch(
    dependencies: Sequence[DeclaredDependency],
    *,
    cache: VulnScanCache | None = None,
    timeout_seconds: float = _OSV_TIMEOUT_SECONDS,
    resolve_severity: bool = True,
) -> list[AdvisoryFinding]:
    """Query OSV.dev in batch for declared dependencies.

    A dependency pinned to an exact version is matched against that version; any other spec matches every version
    of the package. Findings are cached per package version only once all their advisory records were resolved, so
    a transient failure is retried by the next scan instead of being remembered with a default severity.

    Args:
        dependencies: List of dependencies extracted from manifests.
        cache: Optional VulnScanCache instance (uses default global cache if None).
        timeout_seconds: HTTP request timeout in seconds.
        resolve_severity: Fetch every distinct advisory's full record for its real severity and text. That costs one
            more request per advisory, so a caller with a tight time budget can pass False: findings then carry the
            advisory id only, rated CRITICAL for malware and MEDIUM otherwise, and a dependency that has advisories
            is not cached.

    Returns:
        List of AdvisoryFinding discovered from OSV.
    """
    if not dependencies:
        return []

    active_cache = cache if cache is not None else get_vuln_cache()
    findings: list[AdvisoryFinding] = []
    uncached_deps: list[DeclaredDependency] = []

    for dep in dependencies:
        cached = active_cache.get(dep.ecosystem, dep.name, dep.version_spec)
        if cached is None:
            uncached_deps.append(dep)
        else:
            # The cache is keyed by package version, so the dependency's own file and spec are re-attached.
            findings.extend(
                replace(f, matched_version=dep.version_spec or "*", file_path=dep.file_path, source="osv_api")
                for f in cached
            )

    if not uncached_deps:
        return findings

    try:
        async with create_httpx_client(timeout=timeout_seconds) as client:
            semaphore = asyncio.Semaphore(_MAX_CONCURRENT_REQUESTS)
            advisory_ids_per_dep = await _query_advisory_ids(client, uncached_deps, semaphore)
            wanted_ids = {advisory_id for ids in advisory_ids_per_dep if ids for advisory_id in ids}
            records = await _fetch_records(client, wanted_ids, semaphore) if resolve_severity else {}
    except Exception as exc:  # Fail open: an unusable OSV client must not break the caller's scan.
        logger.warning("OSV client failed (%s); dependencies without a cached result were not checked.", exc)
        return findings

    for dep, advisory_ids in zip(uncached_deps, advisory_ids_per_dep, strict=True):
        if advisory_ids is None:
            continue
        dep_findings = [_build_finding(dep, advisory_id, records.get(advisory_id)) for advisory_id in advisory_ids]
        findings.extend(dep_findings)
        if all(advisory_id in records for advisory_id in advisory_ids):
            active_cache.set(dep.ecosystem, dep.name, dep.version_spec, dep_findings)

    unresolved = wanted_ids - records.keys()
    if resolve_severity and unresolved:
        logger.warning(
            "OSV records unavailable for %d advisories; their severity defaults to MEDIUM and they are not cached.",
            len(unresolved),
        )
    return findings
