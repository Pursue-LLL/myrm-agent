from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fluent.runtime import FluentLocalization, FluentResourceLoader

logger = logging.getLogger(__name__)


class SafeDict(dict):
    """A dictionary that returns the key wrapped in braces for missing keys."""
    def __missing__(self, key: str) -> str:
        return f"{{{key}}}"


def _flatten_dict(d: dict[str, Any], parent_key: str = "", sep: str = "_") -> dict[str, Any]:
    """Recursively flatten a nested dictionary."""
    items: list[tuple[str, Any]] = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(_flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


class I18nEngine:
    """Fluent-based i18n engine with BCP 47 fallback support and JSON loading."""

    def __init__(self) -> None:
        self._roots: list[str] = []
        self._localizations: dict[str, FluentLocalization] = {}
        self._json_catalogs: dict[str, dict[str, Any]] = {}
        self._loader: FluentResourceLoader | None = None
        self._default_locale = "en"

        # Register harness default locales
        harness_locales = Path(__file__).parent / "locales"
        if harness_locales.exists():
            self.add_root(str(harness_locales))

    def add_root(self, path: str) -> None:
        """Add a directory to search for .ftl and .json files."""
        if path not in self._roots:
            # Insert at the beginning so newer roots (like Server) override older ones (like Harness)
            self._roots.insert(0, path)
            self._loader = FluentResourceLoader(self._roots)
            self._localizations.clear()  # Clear cache
            self._json_catalogs.clear()  # Clear JSON cache

    def _get_fallback_chain(self, locale: str) -> list[str]:
        """Generate a BCP 47 fallback chain.
        e.g., 'zh-TW' -> ['zh-TW', 'zh-Hant', 'zh-CN', 'zh', 'en']
        """
        chain = [locale]
        parts = locale.replace("_", "-").split("-")

        # Basic BCP 47 fallback (strip subtags)
        while len(parts) > 1:
            parts.pop()
            chain.append("-".join(parts))

        # Specific regional fallbacks
        lower_locale = locale.lower()
        if lower_locale in ("zh-tw", "zh-hk", "zh-mo"):
            if "zh-Hant" not in chain:
                chain.append("zh-Hant")
            if "zh-CN" not in chain:
                chain.append("zh-CN")
        elif lower_locale.startswith("zh"):
            if "zh-CN" not in chain:
                chain.append("zh-CN")

        if self._default_locale not in chain:
            chain.append(self._default_locale)

        return chain

    def _load_json_catalog(self, locale: str) -> dict[str, Any]:
        """Load JSON translations for a locale across all roots."""
        if locale in self._json_catalogs:
            return self._json_catalogs[locale]

        catalog: dict[str, Any] = {}
        # Iterate in reverse so newer roots (at index 0) override older ones
        for root in reversed(self._roots):
            json_path = Path(root) / f"{locale}.json"
            if json_path.exists():
                try:
                    with open(json_path, encoding="utf-8") as f:
                        data = json.load(f)
                        # Flatten the entire JSON dictionary recursively
                        flat_data = _flatten_dict(data)
                        catalog.update(flat_data)
                except Exception as e:
                    logger.warning("Failed to load JSON locale %s: %s", json_path, e)

        self._json_catalogs[locale] = catalog
        return catalog

    def _get_localization(self, locale: str) -> FluentLocalization:
        """Get or create a FluentLocalization instance for the locale."""
        if locale in self._localizations:
            return self._localizations[locale]

        if not self._loader:
            self._loader = FluentResourceLoader(self._roots)

        chain = self._get_fallback_chain(locale)
        # We use {locale}.ftl as the resource name
        l10n = FluentLocalization(chain, ["{locale}.ftl"], self._loader)
        self._localizations[locale] = l10n
        return l10n

    def format_value(self, locale: str | None, key: str, **kwargs: Any) -> Any:
        """Format a message using Fluent or JSON."""
        target_locale = locale or self._default_locale
        chain = self._get_fallback_chain(target_locale)

        # 1. Try JSON catalogs first (Server overrides)
        for loc in chain:
            catalog = self._load_json_catalog(loc)
            if key in catalog:
                val = catalog[key]
                try:
                    safe_kwargs = SafeDict(**kwargs)
                    if isinstance(val, str):
                        return val.format_map(safe_kwargs)
                    elif isinstance(val, list):
                        return [
                            v.format_map(safe_kwargs) if isinstance(v, str) else v for v in val
                        ]
                    return val
                except Exception as exc:
                    logger.warning("JSON format failed: key=%r locale=%r error=%s", key, loc, exc)
                    return val

        # 2. Try Fluent
        l10n = self._get_localization(target_locale)
        try:
            val = l10n.format_value(key, kwargs)
            if val != key:
                return val
        except Exception as exc:
            logger.warning(
                "i18n format failed: key=%r locale=%r error=%s", key, target_locale, exc
            )

        logger.debug("i18n miss: key=%r locale=%r", key, target_locale)
        return key


_engine = I18nEngine()


def add_locale_root(path: str) -> None:
    """Register a new directory containing .ftl or .json files."""
    _engine.add_root(path)


def channel_t(locale: str | None, key: str, **kwargs: Any) -> Any:
    """Translate a catalog key for the given locale using Fluent or JSON."""
    return _engine.format_value(locale, key, **kwargs)
