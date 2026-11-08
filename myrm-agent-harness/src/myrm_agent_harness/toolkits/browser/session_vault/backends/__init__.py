"""Storage backends for SessionVault.

[INPUT]
- (none — standalone module)

[OUTPUT]
- SessionVaultBackend: Storage backend protocol
- FileVaultBackend: Local filesystem backend implementation

[POS]
Storage backend abstraction layer for SessionVault. Defines interfaces via Protocol,
implemented by the local file backend; a host plugs in others.
"""

from .file_backend import FileVaultBackend
from .protocols import SessionVaultBackend

__all__ = ["FileVaultBackend", "SessionVaultBackend"]
