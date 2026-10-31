"""Storage configuration


[INPUT]
- dataclasses::dataclass (POS: Python dataclass)
- pathlib::Path (POS: path handling)
- infra.data_dir::resolve_data_dir (POS: Single entry point for the Myrm state root; harness and server code derive every state path from it)

[OUTPUT]
- StorageConfig: storage configuration (root directory of the filesystem backend)
- storage_config: global storage configuration singleton

[POS]
Storage configuration module. The storage root is ``<state root>/storage``; the deployment layer injects
MYRM_DATA_DIR (in cloud sandboxes it points at the persistent volume). Depended on by the
storage factory and by consumers that need the root directory on disk.
"""

from dataclasses import dataclass, field
from pathlib import Path

from myrm_agent_harness.infra.data_dir import resolve_data_dir


def _get_default_storage_path() -> str:
    """Resolve the default storage path.

    Lives at ``<state root>/storage``; the state root is MYRM_DATA_DIR, default ``~/.myrm``.
    """
    return str(resolve_data_dir().resolve() / "storage")


@dataclass
class StorageConfig:
    """Storage configuration."""

    # The key layout under the root belongs to the business layer; this layer only resolves keys against it.
    base_path: str = field(default_factory=_get_default_storage_path)

    def get_base_path(self) -> Path:
        """Absolute storage root; a relative ``base_path`` is resolved against the current working directory."""
        path = Path(self.base_path)
        if path.is_absolute():
            return path
        return (Path.cwd() / path).resolve()


# Global configuration instance
storage_config = StorageConfig()
