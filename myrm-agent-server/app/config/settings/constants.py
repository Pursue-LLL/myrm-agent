"""[OUTPUT]
- BASE_DIR

[POS]
Repository base directory for configuration defaults.
"""

from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
