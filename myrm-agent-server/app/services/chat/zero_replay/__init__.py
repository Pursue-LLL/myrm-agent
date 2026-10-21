"""[INPUT]
- .service: ZeroReplaySnapshotService

[OUTPUT]
- ZeroReplaySnapshotService: Public facade for zero-replay reconnect service

[POS]
Service package facade for Zero-Replay reconnect protocol (Item 36 P0).
"""

from .service import ZeroReplaySnapshotService

__all__ = ["ZeroReplaySnapshotService"]
