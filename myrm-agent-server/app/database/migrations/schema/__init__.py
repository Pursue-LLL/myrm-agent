"""Schema migration statements 的顺序拼接出口。"""

from __future__ import annotations

from app.database.migrations.schema.v000_124 import STATEMENTS as _P1
from app.database.migrations.schema.v125_245 import STATEMENTS as _P2

STATEMENTS: list[str] = [*_P1, *_P2]
