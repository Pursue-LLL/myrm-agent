"""Environment mode helpers.

Provides is_debug_mode() for development-specific features like
detailed error messages, verbose logging, and relaxed security checks.
"""

import os


def is_debug_mode() -> bool:
    """Check if running in debug/development mode.

    Returns:
        True if DEBUG env var is set to true/1/yes (case-insensitive)
    """
    return os.getenv("DEBUG", "").lower() in ("true", "1", "yes")


__all__ = ["is_debug_mode"]
