"""Security core package.

[INPUT]
- .master_key::MasterKeyProvider (POS: Master key provider)

[OUTPUT]
- MasterKeyProvider: Master key provider export

[POS]
Core security initialization module.
"""

from .master_key import MasterKeyProvider

__all__ = ["MasterKeyProvider"]
