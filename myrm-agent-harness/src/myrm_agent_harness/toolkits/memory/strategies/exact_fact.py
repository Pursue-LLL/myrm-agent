"""Exact fact classification and identifier extraction strategy.

Provides zero-LLM deterministic classification of high-entropy exact facts
(UUIDs, Git SHAs, SemVer tags, network endpoints, system configuration keys)
to support physical dual-track governance and prevent lossy memory compression.

[INPUT]
- str: raw text content or query string
- dict[str, str | int | float | bool] | None: optional memory metadata

[OUTPUT]
- identifier_key: comparison form of an identifier (case-insensitive, without the ``v`` of a version tag)
- ExactFactClassifier.extract_identifiers: extract unique high-entropy tokens and identifiers
- ExactFactClassifier.is_exact_fact: determine if text constitutes an exact fact
- ExactFactClassifier.classify: tuple of (is_exact_fact, extracted_identifiers)
- ExactFactClassifier.query_keys / mentions_any: decide whether a query names a stored identifier

[POS]
Harness-level deterministic classifier in memory/strategies. Decoupled from LLM
runtime and business layers. Fully compatible with SQLite FTS5 inverted indexing.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

# Pre-compiled high-precision regex patterns for exact identifiers.
# ASCII mode keeps ``\b`` and ``\d`` from counting CJK letters as word characters; otherwise an identifier
# written right against Chinese text ("地址是10.0.0.5:8080") has no word boundary and is missed.
#
# Addresses and versions are dotted-number runs. Neither may be read out of the middle of a longer run, so
# the left edge refuses a preceding word character or ".", and the right edge a following ".digit"; without
# that, "10.0.0.5" would also yield the version-looking fragment "10.0.0" shared by its whole subnet.
_LEFT_EDGE = r"(?<![A-Za-z0-9_.])"
_RIGHT_EDGE = r"\b(?!\.[0-9])"
_IPV4_OCTET = r"(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)"
_UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b", re.ASCII
)
_GIT_SHA_PATTERN = re.compile(r"\b[0-9a-fA-F]{40}\b|\b[0-9a-fA-F]{7,12}\b", re.ASCII)
_SEMVER_PATTERN = re.compile(
    rf"{_LEFT_EDGE}v?(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-[0-9a-zA-Z.-]+)?(?:\+[0-9a-zA-Z.-]+)?{_RIGHT_EDGE}",
    re.ASCII,
)
# An address is identified as written: "10.0.0.5:8080" is one identifier and a bare "10.0.0.5" is another.
_NETWORK_ENDPOINT_PATTERN = re.compile(
    rf"{_LEFT_EDGE}(?:{_IPV4_OCTET}\.){{3}}{_IPV4_OCTET}(?::[1-9][0-9]{{0,4}})?{_RIGHT_EDGE}"
    r"|\blocalhost:[1-9][0-9]{0,4}\b",
    re.ASCII,
)
_CONFIG_KEY_PATTERN = re.compile(r"\b[A-Z][A-Z0-9_]{3,}[A-Z0-9]\b", re.ASCII)
# The keyword may itself be CJK (端口), so its left edge is "no ASCII word character before it"; the
# separator accepts the full-width colon and ideographic space Chinese input produces.
_PORT_DECLARATION_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?:port|PORT|端口)[:：\s\u3000=]+([1-9][0-9]{1,4})\b", re.ASCII
)

# Common words matching hex/config patterns that are pure false-positives
_CONFIG_DENYLIST = frozenset(
    {
        "THE",
        "AND",
        "FOR",
        "NOT",
        "WITH",
        "THIS",
        "THAT",
        "FROM",
        "HAVE",
        "USER",
        "TRUE",
        "FALSE",
        "NONE",
        "NULL",
        "INFO",
        "WARN",
        "DEBUG",
        "ERROR",
        "FATAL",
        "HTTP",
        "HTTPS",
        "JSON",
        "YAML",
        "HTML",
        "REST",
        "GRPC",
        "TODO",
        "NOTE",
    }
)

# Words that look like short hex SHAs but are common English words
_HEX_DENYLIST = frozenset(
    {
        "decade",
        "defaced",
        "accord",
        "afford",
        "beefed",
        "coffee",
        "facade",
        "added",
        "dead",
        "beef",
        "fade",
        "face",
        "deed",
        "feed",
        "cede",
        "cafe",
    }
)


# A query is cut into candidate tokens wherever a character cannot belong to an identifier, so "MAX_RETRY=3",
# "http://10.0.0.5:8080/api" and "地址10.0.0.5:8080，" each expose their identifier whole.
_QUERY_CHUNK_PATTERN = re.compile(r"[A-Za-z0-9_.:-]+")
# "v2.4.1" and "2.4.1" name the same version, while a bare "v8" is no version tag.
_VERSION_TAG_PREFIX = re.compile(r"^v(?=[0-9]+\.[0-9]+\.[0-9]+)")


def identifier_key(identifier: str) -> str:
    """Case-insensitive comparison form of an identifier, without the ``v`` of a version tag."""
    return _VERSION_TAG_PREFIX.sub("", identifier.lower())


class ExactFactClassifier:
    """Zero-LLM deterministic classifier for exact facts and high-entropy identifiers."""

    @staticmethod
    def extract_identifiers(text: str) -> list[str]:
        """Extract deduplicated high-entropy tokens and identifiers from text.

        Preserves original casing while preventing duplicate matches.
        """
        if not text or not text.strip():
            return []

        identifiers: list[str] = []
        seen: set[str] = set()

        def _add(match_val: str) -> None:
            cleaned = match_val.strip()
            lower = cleaned.lower()
            if lower not in seen:
                seen.add(lower)
                identifiers.append(cleaned)

        # 1. UUID extraction (RFC 4122)
        for m in _UUID_PATTERN.finditer(text):
            _add(m.group(0))

        # 2. Network endpoint extraction
        for m in _NETWORK_ENDPOINT_PATTERN.finditer(text):
            _add(m.group(0))

        # 3. Port declaration extraction
        for m in _PORT_DECLARATION_PATTERN.finditer(text):
            _add(m.group(1))

        # 4. SemVer version extraction
        for m in _SEMVER_PATTERN.finditer(text):
            val = m.group(0)
            # Filter trivial single digits like '1.0' that aren't semver
            if val.count(".") >= 2:
                _add(val)

        # 5. Config keys (ALL_CAPS identifiers)
        for m in _CONFIG_KEY_PATTERN.finditer(text):
            val = m.group(0)
            if val not in _CONFIG_DENYLIST and "_" in val:
                _add(val)

        # 6. Git commit SHA extraction (full 40 or short 7~12)
        for m in _GIT_SHA_PATTERN.finditer(text):
            val = m.group(0)
            lower = val.lower()
            if lower in _HEX_DENYLIST:
                continue
            # For short hashes (7-12), enforce that it has both letters and numbers
            if len(val) < 16:
                has_digit = any(c.isdigit() for c in val)
                has_alpha = any(c.isalpha() for c in val)
                if has_digit and has_alpha:
                    _add(val)
            else:
                _add(val)

        return identifiers

    @classmethod
    def is_exact_fact(
        cls,
        text: str,
        metadata: Mapping[str, str | int | float | bool] | None = None,
    ) -> bool:
        """Determine if a memory or input text constitutes an exact fact.

        Returns True if:
        1. Explicitly marked via metadata (e.g. metadata['is_exact_fact'] is True)
        2. Text contains at least one validated high-entropy identifier (UUID, SHA, SemVer, config key)
        """
        if metadata:
            explicit_flag = metadata.get("is_exact_fact")
            if isinstance(explicit_flag, bool):
                return explicit_flag

        identifiers = cls.extract_identifiers(text)
        return len(identifiers) > 0

    @classmethod
    def classify(
        cls,
        text: str,
        metadata: Mapping[str, str | int | float | bool] | None = None,
    ) -> tuple[bool, list[str]]:
        """Classify text and return both the boolean verdict and extracted identifiers."""
        identifiers = cls.extract_identifiers(text)
        if metadata and metadata.get("is_exact_fact") is True:
            return True, identifiers
        return len(identifiers) > 0, identifiers

    @classmethod
    def query_keys(cls, query: str) -> frozenset[str]:
        """Comparison keys of every identifier the query can be naming.

        A stored identifier counts as named only when it is a complete token of the query, one of the
        identifiers extracted from it, or the port of an endpoint it contains. Containment is not enough:
        ``22`` is not named by ``2022``, nor ``10.0.0.5`` by ``10.0.0.55``.
        """
        extracted = cls.extract_identifiers(query)
        endpoint_ports = (identifier.rsplit(":", 1)[1] for identifier in extracted if ":" in identifier)
        chunks = (chunk.strip(".:-") for chunk in _QUERY_CHUNK_PATTERN.findall(query))
        return frozenset(identifier_key(token) for token in (*chunks, *extracted, *endpoint_ports) if token)

    @staticmethod
    def mentions_any(identifiers: Iterable[str], query_keys: frozenset[str]) -> bool:
        """Whether any of ``identifiers`` is named by the query that produced ``query_keys``."""
        return any(identifier_key(identifier) in query_keys for identifier in identifiers)
