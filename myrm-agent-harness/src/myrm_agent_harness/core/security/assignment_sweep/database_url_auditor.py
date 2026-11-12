"""Database DSN auditor evaluating loopback host exemptions and remote leak blocking.

[INPUT]
- core.security.assignment_sweep.types::DatabaseUrlAuditResult (POS: Contract layer of the assignment sweep: the key-family, notation and verdict enums plus the finding, report and DSN-audit models shared by the sweep engine and the database URL auditor.)

[OUTPUT]
- DatabaseUrlAuditor: finds database connection URIs (postgres, mysql, mongodb, redis, amqp) in text and rates each one

[POS]
Database-URL leg of the assignment sweep: recognizes connection URIs that carry credentials and decides whether each is an
exempt local-development DSN or a leak; only a loopback host with a standard development credential pair is exempt.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from .types import DatabaseUrlAuditResult

logger = logging.getLogger(__name__)

# Pattern detecting typical connection URIs
_DATABASE_URL_RE = re.compile(
    r"(?P<scheme>postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis(?:s)?|amqps?)"
    r"://(?P<user>[^:@\s]+)(?::(?P<password>[^@\s]*))?"
    r"@(?P<host>[^:/\s?#]+)(?::(?P<port>\d+))?(?P<path>/[^\s?#]*)?",
    re.IGNORECASE,
)

_LOOPBACK_HOSTS: frozenset[str] = frozenset({"localhost", "127.0.0.1", "::1"})

_COMMON_DEV_CREDENTIAL_PAIRS: frozenset[tuple[str, str]] = frozenset(
    {
        ("postgres", "postgres"),
        ("postgres", "root"),
        ("postgres", "password"),
        ("postgres", ""),
        ("root", "root"),
        ("root", "password"),
        ("root", ""),
        ("admin", "admin"),
        ("admin", "password"),
        ("guest", "guest"),
        ("test", "test"),
        ("user", "password"),
    }
)


class DatabaseUrlAuditor:
    """Audits database connection strings for leak risks with legitimate local dev exemption."""

    @staticmethod
    def audit_url(raw_url: str) -> DatabaseUrlAuditResult | None:
        """Analyze a database URL string and return audit assessment if recognized."""
        match = _DATABASE_URL_RE.search(raw_url)
        if match is None:
            # Try urllib fallback if scheme matched partially
            try:
                parsed = urlparse(raw_url)
                if parsed.scheme.lower() in {"postgres", "postgresql", "mysql", "mongodb", "redis", "amqp"}:
                    host = (parsed.hostname or "").lower()
                    user = parsed.username or ""
                    pwd = parsed.password or ""
                    is_loopback = host in _LOOPBACK_HOSTS
                    is_default = (user.lower(), pwd.lower()) in _COMMON_DEV_CREDENTIAL_PAIRS
                    is_exempt = is_loopback and is_default
                    reason = (
                        "Loopback host with standard development credentials exempted"
                        if is_exempt
                        else "Database connection string containing sensitive credentials targeted to external host"
                    )
                    return DatabaseUrlAuditResult(
                        raw_url=raw_url,
                        scheme=parsed.scheme,
                        host=host,
                        user=user,
                        is_loopback=is_loopback,
                        is_default_credential=is_default,
                        is_exempt=is_exempt,
                        audit_reason=reason,
                    )
            except Exception:
                return None
            return None

        scheme = match.group("scheme").lower()
        user = match.group("user")
        password = match.group("password") or ""
        host = match.group("host").lower()

        is_loopback = host in _LOOPBACK_HOSTS
        is_default = (user.lower(), password.lower()) in _COMMON_DEV_CREDENTIAL_PAIRS

        # Crucial security rule: Loopback with default credentials is safe for local development,
        # but ANY non-loopback host (including container service names like @db or @postgres)
        # MUST remain strictly non-exempt to prevent lateral credential exposure.
        is_exempt = is_loopback and is_default

        if is_exempt:
            reason = f"Exempted local development DSN on loopback host '{host}' with standard default credentials"
        elif is_loopback and not is_default:
            reason = f"Flagged DSN on loopback host '{host}' using non-default custom credentials"
        elif not is_loopback and is_default:
            reason = f"Flagged DSN on non-loopback host/service '{host}' despite default credentials"
        else:
            reason = f"Active high-risk DSN exposure targeting non-loopback host '{host}'"

        return DatabaseUrlAuditResult(
            raw_url=raw_url,
            scheme=scheme,
            host=host,
            user=user,
            is_loopback=is_loopback,
            is_default_credential=is_default,
            is_exempt=is_exempt,
            audit_reason=reason,
        )

    @classmethod
    def extract_and_audit_all(cls, text: str) -> list[DatabaseUrlAuditResult]:
        """Find and audit all database URLs occurring in text."""
        results: list[DatabaseUrlAuditResult] = []
        for m in _DATABASE_URL_RE.finditer(text):
            dsn_str = m.group(0)
            res = cls.audit_url(dsn_str)
            if res is not None:
                results.append(res)
        return results
