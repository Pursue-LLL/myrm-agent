"""Measured outcome of span export.

[INPUT]
- (none: plain data, importable without the OpenTelemetry SDK)

[OUTPUT]
- ExportStats: exported / failed / withheld counters and the last success and failure times

[POS]
The exporter-boundary guard writes it; the posture probe reads it. Keeping the type SDK-free lets
the probe answer "is telemetry actually leaving, and is it failing" without importing an exporter.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExportStats:
    """What the exporter actually did, as measured at the export boundary.

    ``withheld_spans`` counts spans the privacy guard could not sanitize and therefore never sent. A span the
    ``BatchSpanProcessor`` discards because its queue is full never reaches the guard and is in no counter.
    """

    exported_spans: int = 0
    failed_batches: int = 0
    withheld_spans: int = 0
    last_success_at: float | None = None
    last_failure_at: float | None = None

    @property
    def attempted(self) -> bool:
        """True once the exporter has tried to send a batch, whatever the outcome."""
        return self.last_success_at is not None or self.last_failure_at is not None

    @property
    def last_export_failed(self) -> bool:
        """True when the most recent export attempt failed."""
        if self.last_failure_at is None:
            return False
        return self.last_success_at is None or self.last_failure_at > self.last_success_at
