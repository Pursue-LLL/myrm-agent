"""Code graph SQLite store for persistent AST symbols and deterministic call edges.

[INPUT]
- models.py::(ParsedFile, SymbolKind, SymbolNode)
- sqlite3

[OUTPUT]
- CodeGraphStore: SQLite WAL 持久化代码图谱存储：按文件指纹增量同步与确定性图遍历查询

[POS]
Server 业务服务层。提供本地轻量级代码 AST 符号图谱与调用关系持久化存储库。
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from collections.abc import Generator, Iterable, Sequence
from contextlib import contextmanager
from pathlib import Path

from app.services.code_graph.models import ParsedFile, SymbolKind, SymbolNode

# 测试文件按路径约定识别：tests/ 或 __tests__/ 目录、test_*.py、*_test.py、*.test.* 与 *.spec.*。
_TEST_FILE_PATTERN = re.compile(r"(^|/)(tests?|__tests__)/|(^|/)test_[^/]*\.py$|_test\.py$|\.(test|spec)\.[jt]sx?$")
_INDEX_TABLES = ("symbols", "calls", "inheritances", "imports", "files")


# Switching a new database to WAL needs it briefly to itself and, unlike other statements, does not wait on the
# busy timeout; two agents opening the same workspace at once would make one of them fail.
_WAL_ATTEMPTS = 50
_WAL_RETRY_SECONDS = 0.1


def _enable_wal(conn: sqlite3.Connection) -> None:
    for attempt in range(_WAL_ATTEMPTS):
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            return
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc) or attempt == _WAL_ATTEMPTS - 1:
                raise
            time.sleep(_WAL_RETRY_SECONDS)


def _escape_like(text: str) -> str:
    """Make ``text`` match literally inside a LIKE pattern (``_`` and ``%`` are wildcards otherwise)."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class CodeGraphStore:
    """基于 SQLite WAL 模式的高性能本地代码图谱持久化存储。"""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            _enable_wal(conn)
            conn.execute("PRAGMA synchronous=NORMAL;")
            cursor = conn.cursor()

            # 1. 符号表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS symbols (
                    qualified_name TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    line_start INTEGER NOT NULL,
                    line_end INTEGER NOT NULL,
                    docstring TEXT
                );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sym_name ON symbols(name);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sym_file ON symbols(file_path);")

            # 2. 调用关系表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    caller TEXT NOT NULL,
                    callee TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    line INTEGER NOT NULL,
                    col INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    end_col INTEGER NOT NULL,
                    arg_count INTEGER NOT NULL,
                    kwarg_names TEXT
                );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_call_caller ON calls(caller);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_call_callee ON calls(callee);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_call_file ON calls(file_path);")

            # 3. 继承与实现关系表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS inheritances (
                    sub_type TEXT NOT NULL,
                    super_type TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    line INTEGER NOT NULL,
                    PRIMARY KEY(sub_type, super_type)
                );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_inh_super ON inheritances(super_type);")

            # 4. 模块导入表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS imports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    importer_module TEXT NOT NULL,
                    imported_symbol TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    line INTEGER NOT NULL,
                    col INTEGER NOT NULL,
                    alias TEXT
                );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_imp_symbol ON imports(imported_symbol);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_imp_file ON imports(file_path);")

            # 5. 文件指纹：增量同步据此判断哪些文件变了、没了
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    file_path TEXT PRIMARY KEY,
                    mtime_ns INTEGER NOT NULL,
                    size INTEGER NOT NULL
                );
            """)

            conn.commit()

    def get_file_fingerprints(self) -> dict[str, tuple[int, int]]:
        """Indexed files with the (mtime_ns, size) they had when they were parsed."""
        with self._get_conn() as conn:
            rows = conn.execute("SELECT file_path, mtime_ns, size FROM files").fetchall()
            return {row["file_path"]: (row["mtime_ns"], row["size"]) for row in rows}

    def apply_changes(self, *, removed: Iterable[str], parsed: Sequence[ParsedFile], reset: bool = False) -> None:
        """Forget ``removed`` files, replace every entry of the ``parsed`` files, all in one transaction.

        ``reset`` empties the store first, for a store whose entries have no recorded provenance.
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()
            if reset:
                for table in _INDEX_TABLES:
                    cursor.execute(f"DELETE FROM {table}")
            else:
                stale = [(path,) for path in (*removed, *(f.file_path for f in parsed))]
                for table in _INDEX_TABLES:
                    cursor.executemany(f"DELETE FROM {table} WHERE file_path = ?", stale)

            cursor.executemany(
                "INSERT OR REPLACE INTO files (file_path, mtime_ns, size) VALUES (?, ?, ?)",
                [(f.file_path, f.mtime_ns, f.size) for f in parsed],
            )
            cursor.executemany(
                """
                INSERT OR REPLACE INTO symbols
                (qualified_name, name, kind, file_path, line_start, line_end, docstring)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (s.qualified_name, s.name, s.kind.value, s.file_path, s.line_start, s.line_end, s.docstring)
                    for f in parsed
                    for s in f.symbols
                ],
            )
            cursor.executemany(
                """
                INSERT INTO calls
                (caller, callee, file_path, line, col, end_line, end_col, arg_count, kwarg_names)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        c.caller,
                        c.callee,
                        c.call_site.file_path,
                        c.call_site.line,
                        c.call_site.col,
                        c.call_site.end_line,
                        c.call_site.end_col,
                        c.call_site.arg_count,
                        json.dumps(c.call_site.kwarg_names),
                    )
                    for f in parsed
                    for c in f.calls
                ],
            )
            cursor.executemany(
                "INSERT OR IGNORE INTO inheritances (sub_type, super_type, file_path, line) VALUES (?, ?, ?, ?)",
                [(i.sub_type, i.super_type, i.file_path, i.line) for f in parsed for i in f.inheritances],
            )
            cursor.executemany(
                """
                INSERT INTO imports
                (importer_module, imported_symbol, file_path, line, col, alias)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [(i.importer_module, i.imported_symbol, i.file_path, i.line, i.col, i.alias) for f in parsed for i in f.imports],
            )
            conn.commit()

    def get_symbol(self, qualified_name: str) -> SymbolNode | None:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM symbols WHERE qualified_name = ? LIMIT 1",
                (qualified_name,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return SymbolNode(
                qualified_name=row["qualified_name"],
                name=row["name"],
                kind=SymbolKind(row["kind"]),
                file_path=row["file_path"],
                line_start=row["line_start"],
                line_end=row["line_end"],
                docstring=row["docstring"] or "",
            )

    def resolve_names(self, target: str, limit: int = 20) -> list[dict[str, object]]:
        suffix = f"%.{_escape_like(target)}"
        with self._get_conn() as conn:
            cursor = conn.cursor()
            # 1. path:line 模式
            if ":" in target and not target.endswith(":"):
                parts = target.split(":")
                f_path = parts[0]
                try:
                    line_no = int(parts[1])
                    cursor.execute(
                        """
                        SELECT qualified_name, name, kind, file_path, line_start, line_end
                        FROM symbols
                        WHERE file_path = ? AND line_start <= ? AND line_end >= ?
                        ORDER BY (line_end - line_start) ASC
                        """,
                        (f_path, line_no, line_no),
                    )
                    return [dict(r) for r in cursor.fetchall()]
                except ValueError:
                    pass

            # 2. 精确匹配 -> 后缀匹配 -> 纯名称匹配
            cursor.execute(
                """
                SELECT qualified_name, name, kind, file_path, line_start, line_end,
                CASE 
                    WHEN qualified_name = ? THEN 1
                    WHEN qualified_name LIKE ? ESCAPE '\\' THEN 2
                    WHEN name = ? THEN 3
                    ELSE 4
                END as priority
                FROM symbols
                WHERE qualified_name = ? OR qualified_name LIKE ? ESCAPE '\\' OR name = ?
                ORDER BY priority ASC, qualified_name ASC
                LIMIT ?
                """,
                (target, suffix, target, target, suffix, target, limit),
            )
            return [dict(r) for r in cursor.fetchall()]

    def get_callers(self, callee_name: str) -> list[dict[str, object]]:
        """Call sites whose callee text is ``callee_name`` or ends with its last component.

        The callee is recorded as written at the call site and is never resolved to a definition, so
        ``match`` is ``exact`` only when that text equals ``callee_name``; a ``name`` row shares just the
        last component and may call a different function of the same name.
        """
        bare_name = callee_name.split(".")[-1]
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT caller, callee, file_path, line, col, end_line, end_col, arg_count, kwarg_names
                FROM calls
                WHERE callee = ? OR callee = ? OR callee LIKE ? ESCAPE '\\'
                ORDER BY file_path ASC, line ASC
                """,
                (callee_name, bare_name, f"%.{_escape_like(bare_name)}"),
            )
            rows = cursor.fetchall()
            results = []
            for r in rows:
                item = dict(r)
                item["kwarg_names"] = json.loads(item["kwarg_names"]) if item["kwarg_names"] else []
                item["match"] = "exact" if item["callee"] == callee_name else "name"
                results.append(item)
            return results

    def count_definitions(self, name: str) -> int:
        """Functions, methods and classes sharing the last component of ``name``."""
        bare_name = name.split(".")[-1]
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM symbols WHERE name = ? AND kind IN (?, ?, ?)",
                (bare_name, SymbolKind.FUNCTION.value, SymbolKind.METHOD.value, SymbolKind.CLASS.value),
            ).fetchone()
            return int(row["n"])

    def get_callees(self, caller_qname: str) -> list[dict[str, object]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT caller, callee, file_path, line, col, end_line, end_col, arg_count, kwarg_names
                FROM calls
                WHERE caller = ?
                ORDER BY line ASC
                """,
                (caller_qname,),
            )
            rows = cursor.fetchall()
            results = []
            for r in rows:
                item = dict(r)
                item["kwarg_names"] = json.loads(item["kwarg_names"]) if item["kwarg_names"] else []
                results.append(item)
            return results

    def get_implementors(self, super_type_name: str) -> list[dict[str, object]]:
        bare_name = super_type_name.split(".")[-1]
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT sub_type, super_type, file_path, line
                FROM inheritances
                WHERE super_type = ? OR super_type = ? OR super_type LIKE ? ESCAPE '\\'
                ORDER BY sub_type ASC
                """,
                (super_type_name, bare_name, f"%.{_escape_like(bare_name)}"),
            )
            return [dict(r) for r in cursor.fetchall()]

    def get_importers(self, module_name: str) -> list[dict[str, object]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT importer_module, imported_symbol, file_path, line, col, alias
                FROM imports
                WHERE imported_symbol = ? OR imported_symbol LIKE ? ESCAPE '\\'
                ORDER BY file_path ASC, line ASC
                """,
                (module_name, f"{_escape_like(module_name)}.%"),
            )
            return [dict(r) for r in cursor.fetchall()]

    def get_tests_calling(self, target_qname: str) -> list[dict[str, object]]:
        """Call sites of ``target_qname`` that sit in test files, one row per call site.

        Callers are matched by name (see ``get_callers``), so following them through further hops
        would add unrelated same-named functions; only direct callers are reported.
        """
        return [
            {"test_symbol": row["caller"], "file_path": row["file_path"], "line": row["line"], "match": row["match"]}
            for row in self.get_callers(target_qname)
            if _TEST_FILE_PATTERN.search(Path(str(row["file_path"])).as_posix())
        ]

    def count_totals(self) -> dict[str, int]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as total_files FROM files")
            tf = cursor.fetchone()["total_files"]
            cursor.execute("SELECT COUNT(*) as total_symbols FROM symbols")
            ts = cursor.fetchone()["total_symbols"]
            cursor.execute("SELECT COUNT(*) as total_calls FROM calls")
            tc = cursor.fetchone()["total_calls"]
            return {"total_files": tf, "total_symbols": ts, "total_calls": tc}
