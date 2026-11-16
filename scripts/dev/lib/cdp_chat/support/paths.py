"""Checkout location of the E2E helpers.

[INPUT]
- none: standard library only

[OUTPUT]
- MONOREPO_ROOT: root of the checkout this package lives in

[POS]
Single source of the checkout root the E2E helpers resolve dev scripts and stack state against.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

# <root>/myrm-agent/scripts/dev/lib/cdp_chat/support/paths.py
MONOREPO_ROOT: Final[Path] = Path(__file__).resolve().parents[6]
