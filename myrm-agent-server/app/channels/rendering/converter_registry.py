"""Format Converter Registry — pluggable format conversion system.

Framework-layer utility for registering and executing format converters.
Channels register their converters once at startup; renderer uses registry
for format conversion with automatic fallback chains.

[INPUT]

[OUTPUT]
- FormatConverterRegistry: global converter registration and execution

[POS]
Pluggable format conversion registry. Channels register (source_format,
target_format) → converter_fn; renderer invokes convert() with auto-fallback.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

ConverterFn = Callable[[str], str]


class FormatConverterRegistry:
    """Global registry for format converters (thread-safe, class-level).

    Usage:
        # Channel registration (at startup)
        FormatConverterRegistry.register("markdown", "whatsapp", md_to_whatsapp)

        # Renderer usage
        result = FormatConverterRegistry.convert(text, "markdown", "whatsapp")

        # Auto-fallback
        result = FormatConverterRegistry.auto_fallback(
            text, "whatsapp", fallback_chain=["markdown", "plaintext"]
        )
    """

    _converters: dict[tuple[str, str], ConverterFn] = {}

    @classmethod
    def register(
        cls,
        source_format: str,
        target_format: str,
        converter: ConverterFn,
    ) -> None:
        """Register a format converter.

        Args:
            source_format: Source format name (e.g. "markdown")
            target_format: Target format name (e.g. "whatsapp")
            converter: Conversion function (str → str)

        Example:
            >>> FormatConverterRegistry.register(
            ...     "markdown", "whatsapp",
            ...     lambda text: text.replace("**", "*")
            ... )
        """
        key = (source_format.lower(), target_format.lower())
        if key in cls._converters:
            logger.warning(
                "FormatConverterRegistry: replacing existing converter %s → %s",
                source_format,
                target_format,
            )
        cls._converters[key] = converter
        logger.info(
            "FormatConverterRegistry: registered %s → %s",
            source_format,
            target_format,
        )

    @classmethod
    def convert(
        cls,
        text: str,
        source_format: str,
        target_format: str,
    ) -> str:
        """Convert text from source_format to target_format.

        Returns original text if converter not found.

        Args:
            text: Input text
            source_format: Source format name
            target_format: Target format name

        Returns:
            Converted text, or original text if converter not registered
        """
        if not text:
            return text

        key = (source_format.lower(), target_format.lower())
        converter = cls._converters.get(key)

        if not converter:
            logger.debug(
                "FormatConverterRegistry: no converter for %s → %s, returning original",
                source_format,
                target_format,
            )
            return text

        try:
            return converter(text)
        except Exception as exc:
            logger.error(
                "FormatConverterRegistry: conversion failed %s → %s: %s",
                source_format,
                target_format,
                exc,
                exc_info=True,
            )
            return text  # Fallback to original on error

    @classmethod
    def auto_fallback(
        cls,
        text: str,
        target_format: str,
        fallback_chain: list[str] | None = None,
    ) -> str:
        """Convert with automatic fallback chain.

        Tries each format in fallback_chain until one succeeds.

        Args:
            text: Input text
            target_format: Desired target format
            fallback_chain: List of source formats to try, in order.
                Defaults to ["rich", "markdown", "plaintext"]

        Returns:
            Converted text using first successful converter

        Example:
            >>> FormatConverterRegistry.auto_fallback(
            ...     text, "whatsapp",
            ...     fallback_chain=["markdown", "plaintext"]
            ... )
        """
        if not text:
            return text

        if fallback_chain is None:
            fallback_chain = ["rich", "markdown", "plaintext"]

        for source in fallback_chain:
            converted = cls.convert(text, source, target_format)
            if converted != text:  # Conversion happened
                logger.debug(
                    "FormatConverterRegistry: auto_fallback %s → %s succeeded",
                    source,
                    target_format,
                )
                return converted

        # All converters failed or not registered, return original
        logger.debug("FormatConverterRegistry: auto_fallback exhausted, returning original")
        return text

    @classmethod
    def list_converters(cls) -> list[tuple[str, str]]:
        """List all registered converters.

        Returns:
            List of (source_format, target_format) tuples
        """
        return list(cls._converters.keys())

    @classmethod
    def clear(cls) -> None:
        """Clear all registered converters (for testing)."""
        cls._converters.clear()
