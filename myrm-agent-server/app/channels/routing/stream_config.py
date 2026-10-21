"""Unified configuration for streaming components.

Centralizes all streaming-related configuration parameters for consistent
management across BlockChunker, IncrementalEditor, AdaptiveThrottler,
ProgressEstimator, StreamCoordinator, and GracefulDegradationController.

All parameters have sensible defaults; inject a custom StreamConfig instance
to override.

[INPUT]
- (none)

[OUTPUT]
- StreamConfig: Unified configuration for all streaming components.

[POS]
Unified configuration for streaming components.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StreamConfig:
    """Unified configuration for all streaming components.

    All fields have sensible defaults. Construct directly to customize::

        config = StreamConfig(block_size=1000, max_retries=5)
    """

    block_size: int = 500
    enable_code_fence_protection: bool = True
    prefer_newline_breaks: bool = True

    base_interval_seconds: float = 1.0
    min_interval_seconds: float = 0.3
    max_interval_seconds: float = 3.0

    progress_session_ttl_seconds: float = 3600.0
    coordinator_session_ttl_seconds: float = 3600.0
    min_first_send_size: int = 50

    max_retries: int = 3
    base_retry_delay_seconds: float = 0.5

    enable_compression: bool = False
    compression_min_size: int = 500
