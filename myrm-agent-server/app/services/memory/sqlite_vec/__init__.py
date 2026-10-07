"""Embedded SQLite vector service package.

[POS]
Exports service provider and factory for single-file embedded SQLite vector storage.

[INPUT]
- .provider (SqliteVecProvider, get_sqlite_vec_provider)

[OUTPUT]
- SqliteVecProvider, get_sqlite_vec_provider
"""

from app.services.memory.sqlite_vec.provider import (
    SqliteVecProvider,
    get_sqlite_vec_provider,
)

__all__ = [
    "SqliteVecProvider",
    "get_sqlite_vec_provider",
]
