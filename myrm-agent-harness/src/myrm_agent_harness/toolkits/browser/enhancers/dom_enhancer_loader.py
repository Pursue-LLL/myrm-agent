"""DOM Enhancer module.

Provides a script that enhances DOM by exposing React/Vue interactive elements
and injecting SPA stability detection.

[INPUT]
- dom_enhancer.js (bundled asset in same directory)

[OUTPUT]
- get_dom_enhancer_script(): Load and return the dom_enhancer.js script content (successful reads are cached, failed reads are not).

[POS]
DOM enhancer script loader. Bundles and serves the JS enhancer to page init.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _read_dom_enhancer() -> str:
    # Raising keeps a failed read out of the cache: caching its fallback would leave every later
    # context in the process without the enhancer after one transient read error.
    return (Path(__file__).parent / "dom_enhancer.js").read_text(encoding="utf-8")


def get_dom_enhancer_script() -> str:
    """Load and return the dom_enhancer.js script content ("" when it cannot be read; the next call retries)."""
    try:
        return _read_dom_enhancer()
    except Exception as e:
        logger.error(f"Failed to load dom_enhancer.js: {e}")
        return ""
