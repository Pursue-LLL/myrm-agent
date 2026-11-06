"""Index migration statements 的顺序拼接出口。"""

from __future__ import annotations

from app.database.migrations.indexes.v000_102 import STATEMENTS as _P1
from app.database.migrations.indexes.v103_157 import STATEMENTS as _P2

STATEMENTS: list[str] = [*_P1, *_P2]
