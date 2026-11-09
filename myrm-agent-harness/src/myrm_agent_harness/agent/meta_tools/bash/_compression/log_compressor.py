"""Deduplicating compressor for repetitive log streams.

Collapses repeated log messages into counts. Output whose lines are not log records is left untouched: a file
listing, a grep result or a JSON dump repeats after normalisation just like a log does, but every one of its
lines is data the caller asked for.

[INPUT]
- (none — pure regex-based text transformation)

[OUTPUT]
- LogCompressor: log-stream deduplication fallback used by output_compressor.compress_output

[POS]
Fallback compressor for bash tool results that no command-specific compressor claimed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_MIN_LINES = 100
# Share of non-empty lines that must be log records before the output is treated as a log stream.
_MIN_RECORD_SHARE = 0.8
_MAX_ERRORS_SHOWN = 10
_MAX_WARNINGS_SHOWN = 5
_MAX_INFOS_SHOWN = 20

_LOG_TIMESTAMP_RE = re.compile(r"^\d{4}[-/]\d{2}[-/]\d{2}[T ]\d{2}:\d{2}:\d{2}[.,]?\d*\s*")
_LOG_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_LOG_HEX_RE = re.compile(r"0x[0-9a-fA-F]+")
_LOG_NUM_RE = re.compile(r"\b\d{4,}\b")
_LOG_PATH_RE = re.compile(r"/[\w./\-]+")
# A log record opens with an ISO-style, syslog or access-log timestamp, or with its severity.
_LOG_RECORD_RE = re.compile(
    r"^\s*(?:\[?\d{4}[-/]\d{2}[-/]\d{2}[T ]\d{2}:\d{2}:\d{2}"
    r"|[A-Z][a-z]{2}\s+\d{1,2}\s\d{2}:\d{2}:\d{2}"
    r"|\S+\s+\S+\s+\S+\s+\[\d{2}/[A-Z][a-z]{2}/\d{4}:\d{2}:\d{2}:\d{2}"
    r"|\[?(?:TRACE|DEBUG|INFO|NOTICE|WARN(?:ING)?|ERROR|FATAL|CRITICAL|PANIC)\b)",
    re.IGNORECASE,
)
_ERROR_KEYWORDS = ("error", "fatal", "panic", "critical", "alert", "emerg", "severe", "exception")
_WARNING_KEYWORDS = ("warn", "notice")


@dataclass
class _Tally:
    """Distinct normalised messages of one severity: first original line and occurrence count, first-seen order."""

    first_line: dict[str, str] = field(default_factory=dict)
    count: dict[str, int] = field(default_factory=dict)

    def add(self, normalized: str, line: str) -> None:
        self.first_line.setdefault(normalized, line)
        self.count[normalized] = self.count.get(normalized, 0) + 1

    @property
    def total(self) -> int:
        return sum(self.count.values())

    def section(self, title: str, limit: int, noun: str, *, by_frequency: bool) -> list[str]:
        """Lines of one summary section; empty when there is nothing to show."""
        if not self.count:
            return []
        keys = sorted(self.count, key=self.count.__getitem__, reverse=True) if by_frequency else list(self.count)
        rows = [self._row(key) for key in keys[:limit]]
        if len(keys) > limit:
            rows.append(f"  ... +{len(keys) - limit} more {noun}")
        return [title, *rows, ""]

    def _row(self, key: str) -> str:
        count = self.count[key]
        return f"  [×{count}] {self.first_line[key]}" if count > 1 else f"  {self.first_line[key]}"


class LogCompressor:
    """Compress massive repetitive logs: normalize dynamic variables and deduplicate."""

    def compress(self, stdout: str, *, is_failure: bool = False) -> str | None:
        lines = stdout.splitlines()
        if len(lines) < _MIN_LINES or not self._is_log_stream(lines):
            return None

        errors, warnings, infos = _Tally(), _Tally(), _Tally()
        for line in lines:
            normalized = self._normalize(line)
            if not normalized:
                continue
            line_lower = line.lower()
            if any(k in line_lower for k in _ERROR_KEYWORDS):
                errors.add(normalized, line)
            elif any(k in line_lower for k in _WARNING_KEYWORDS):
                warnings.add(normalized, line)
            else:
                infos.add(normalized, line)

        unique_total = len(errors.count) + len(warnings.count) + len(infos.count)
        if unique_total > len(lines) * 0.5:
            return None

        result = [
            "[System Note: Detected massive repetitive logs. Auto-deduplicated.]",
            "Log Summary:",
        ]
        if errors.total > 0:
            result.append(f"  [error] {errors.total} errors ({len(errors.count)} unique)")
        if warnings.total > 0:
            result.append(f"  [warn] {warnings.total} warnings ({len(warnings.count)} unique)")
        if infos.total > 0:
            result.append(f"  [info] {infos.total} info messages")
        result.append("")
        result += errors.section("[ERRORS]", _MAX_ERRORS_SHOWN, "unique errors", by_frequency=True)
        result += warnings.section("[WARNINGS]", _MAX_WARNINGS_SHOWN, "unique warnings", by_frequency=True)
        result += infos.section("[INFO]", _MAX_INFOS_SHOWN, "distinct info messages", by_frequency=False)

        compressed = "\n".join(result).strip()
        return compressed if len(compressed) < len(stdout) else None

    @staticmethod
    def _is_log_stream(lines: list[str]) -> bool:
        records = [line for line in lines if line.strip()]
        log_records = sum(1 for line in records if _LOG_RECORD_RE.match(line))
        return bool(records) and log_records >= _MIN_RECORD_SHARE * len(records)

    @staticmethod
    def _normalize(line: str) -> str:
        normalized = _LOG_TIMESTAMP_RE.sub("", line)
        normalized = _LOG_UUID_RE.sub("<UUID>", normalized)
        normalized = _LOG_HEX_RE.sub("<HEX>", normalized)
        normalized = _LOG_NUM_RE.sub("<NUM>", normalized)
        normalized = _LOG_PATH_RE.sub("<PATH>", normalized)
        return normalized.strip()
