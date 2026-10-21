"""Custom skill source configuration persistence.

[INPUT]
- pathlib::Path (POS: File system path operations)
- json (POS: JSON serialization)

[OUTPUT]
- load_custom_sources, save_custom_sources, add_custom_source, remove_custom_source

[POS]
Manages user-defined custom skill sources (e.g. .well-known/skills/ endpoints).
Stored as JSON under MYRM_DATA_DIR (default ~/.myrm/skill_sources.json).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


def _get_config_path() -> Path:
    data_dir = os.environ.get("MYRM_DATA_DIR", "").strip()
    if data_dir:
        return Path(data_dir).expanduser().resolve() / "skill_sources.json"
    return Path.home() / ".myrm" / "skill_sources.json"


@dataclass(frozen=True)
class CustomSourceEntry:
    """A user-configured custom skill source."""

    url: str
    source_type: str = "well-known"
    label: str = ""
    healthy: bool = True


@dataclass
class CustomSourceConfig:
    """Persisted custom source configuration."""

    sources: list[CustomSourceEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {"sources": [asdict(s) for s in self.sources]}

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> CustomSourceConfig:
        raw_sources = data.get("sources", [])
        sources: list[CustomSourceEntry] = []
        if isinstance(raw_sources, list):
            for item in raw_sources:
                if isinstance(item, dict):
                    sources.append(
                        CustomSourceEntry(
                            url=str(item.get("url", "")),
                            source_type=str(item.get("source_type", "well-known")),
                            label=str(item.get("label", "")),
                            healthy=bool(item.get("healthy", True)),
                        )
                    )
        return cls(sources=sources)


def load_custom_sources() -> CustomSourceConfig:
    """Load custom sources from disk."""
    config_file = _get_config_path()
    if not config_file.exists():
        return CustomSourceConfig()
    try:
        data = json.loads(config_file.read_text(encoding="utf-8"))
        return CustomSourceConfig.from_dict(data)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load custom sources config: %s", e)
        return CustomSourceConfig()


def save_custom_sources(config: CustomSourceConfig) -> None:
    """Persist custom sources to disk."""
    config_file = _get_config_path()
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        json.dumps(config.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def add_custom_source(url: str, source_type: str = "well-known", label: str = "") -> CustomSourceEntry:
    """Add a custom source. Raises ValueError if already exists."""
    config = load_custom_sources()
    if any(s.url == url for s in config.sources):
        raise ValueError(f"Source already exists: {url}")
    entry = CustomSourceEntry(url=url, source_type=source_type, label=label)
    config.sources.append(entry)
    save_custom_sources(config)
    return entry


def remove_custom_source(url: str) -> bool:
    """Remove a custom source by URL. Returns True if removed."""
    config = load_custom_sources()
    new_sources = [s for s in config.sources if s.url != url]
    if len(new_sources) == len(config.sources):
        return False
    config.sources = new_sources
    save_custom_sources(config)
    return True
