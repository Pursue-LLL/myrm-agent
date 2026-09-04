"""Code graph SQLite store for persistent AST symbols and deterministic call edges.

[INPUT]
- models.py::(CallEdge, ImportEdge, InheritanceEdge, SymbolKind, SymbolNode)
- sqlite3

[OUTPUT]
- CodeGraphStore: SQLite WAL 持久化代码图谱存储与 8 大确定性图遍历操作

[POS]
Server 业务服务层。提供本地轻量级代码 AST 符号图谱与调用关系持久化存储库。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from app.services.code_graph.models import (
    CallEdge,
    ImportEdge,
    InheritanceEdge,
    SymbolKind,
    SymbolNode,
)


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
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            cursor = conn.cursor()

            # 1. 符号表
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS symbols (
                    qualified_name TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    line_start INTEGER NOT NULL,
                    line_end INTEGER NOT NULL,
                    docstring TEXT,
                    source TEXT
                );
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sym_name ON symbols(name);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sym_file ON symbols(file_path);")

            # 2. 调用关系表
            cursor.execute(
                """
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
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_call_caller ON calls(caller);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_call_callee ON calls(callee);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_call_file ON calls(file_path);")

            # 3. 继承与实现关系表
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS inheritances (
                    sub_type TEXT NOT NULL,
                    super_type TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    line INTEGER NOT NULL,
                    PRIMARY KEY(sub_type, super_type)
                );
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_inh_super ON inheritances(super_type);")

            # 4. 模块导入表
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS imports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    importer_module TEXT NOT NULL,
                    imported_symbol TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    line INTEGER NOT NULL,
                    col INTEGER NOT NULL,
                    alias TEXT
                );
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_imp_symbol ON imports(imported_symbol);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_imp_file ON imports(file_path);")

            conn.commit()

    def delete_file_entries(self, file_path: str) -> None:
        """增量重析前提：清除单个文件的旧符号与边。"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM symbols WHERE file_path = ?", (file_path,))
            cursor.execute("DELETE FROM calls WHERE file_path = ?", (file_path,))
            cursor.execute("DELETE FROM inheritances WHERE file_path = ?", (file_path,))
            cursor.execute("DELETE FROM imports WHERE file_path = ?", (file_path,))
            conn.commit()

    def batch_insert(
        self,
        symbols: list[SymbolNode],
        calls: list[CallEdge],
        inheritances: list[InheritanceEdge],
        imports: list[ImportEdge],
    ) -> None:
        with self._get_conn() as conn:
            cursor = conn.cursor()

            # 插入符号
            cursor.executemany(
                """
                INSERT OR REPLACE INTO symbols 
                (qualified_name, name, kind, file_path, line_start, line_end, docstring, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        s.qualified_name,
                        s.name,
                        s.kind.value,
                        s.file_path,
                        s.line_start,
                        s.line_end,
                        s.docstring,
                        s.source,
                    )
                    for s in symbols
                ],
            )

            # 插入调用
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
                    for c in calls
                ],
            )

            # 插入继承
            cursor.executemany(
                """
                INSERT OR IGNORE INTO inheritances 
                (sub_type, super_type, file_path, line)
                VALUES (?, ?, ?, ?)
                """,
                [(inh.sub_type, inh.super_type, inh.file_path, inh.line) for inh in inheritances],
            )

            # 插入导入
            cursor.executemany(
                """
                INSERT INTO imports 
                (importer_module, imported_symbol, file_path, line, col, alias)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        imp.importer_module,
                        imp.imported_symbol,
                        imp.file_path,
                        imp.line,
                        imp.col,
                        imp.alias,
                    )
                    for imp in imports
                ],
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
                source=row["source"] or "",
            )

    def resolve_names(self, target: str) -> list[dict[str, object]]:
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
                    WHEN qualified_name LIKE ? THEN 2
                    WHEN name = ? THEN 3
                    ELSE 4
                END as priority
                FROM symbols
                WHERE qualified_name = ? OR qualified_name LIKE ? OR name = ?
                ORDER BY priority ASC, qualified_name ASC
                LIMIT 20
                """,
                (target, f"%.{target}", target, target, f"%.{target}", target),
            )
            return [dict(r) for r in cursor.fetchall()]

    def get_callers(self, callee_name: str) -> list[dict[str, object]]:
        bare_name = callee_name.split(".")[-1]
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT caller, callee, file_path, line, col, end_line, end_col, arg_count, kwarg_names
                FROM calls
                WHERE callee = ? OR callee = ? OR callee LIKE ?
                ORDER BY file_path ASC, line ASC
                """,
                (callee_name, bare_name, f"%.{bare_name}"),
            )
            rows = cursor.fetchall()
            results = []
            for r in rows:
                item = dict(r)
                item["kwarg_names"] = json.loads(item["kwarg_names"]) if item["kwarg_names"] else []
                results.append(item)
            return results

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
                WHERE super_type = ? OR super_type = ? OR super_type LIKE ?
                ORDER BY sub_type ASC
                """,
                (super_type_name, bare_name, f"%.{bare_name}"),
            )
            return [dict(r) for r in cursor.fetchall()]

    def get_importers(self, module_name: str) -> list[dict[str, object]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT importer_module, imported_symbol, file_path, line, col, alias
                FROM imports
                WHERE imported_symbol = ? OR imported_symbol LIKE ?
                ORDER BY file_path ASC, line ASC
                """,
                (module_name, f"{module_name}.%"),
            )
            return [dict(r) for r in cursor.fetchall()]

    def get_tests_reaching(self, target_qname: str) -> list[dict[str, object]]:
        """基于反向调用图追溯所有直接或间接可触达该符号的测试函数或文件。"""
        callers = self.get_callers(target_qname)
        visited_callers: set[str] = set()
        reaching_tests: list[dict[str, object]] = []

        queue = [(c["caller"], c["file_path"], c["line"], 1) for c in callers]

        while queue:
            caller_sym, f_path, line, depth = queue.pop(0)
            if caller_sym in visited_callers:
                continue
            visited_callers.add(caller_sym)

            # 判断是否为测试
            is_test = "test" in f_path.lower() or "test_" in caller_sym.lower()
            if is_test:
                reaching_tests.append(
                    {
                        "test_symbol": caller_sym,
                        "file_path": f_path,
                        "line": line,
                        "distance": depth,
                    }
                )

            # 递归上一级（最多追溯 4 层深度以防成环或暴风雪）
            if depth < 4:
                parent_callers = self.get_callers(caller_sym)
                for pc in parent_callers:
                    if pc["caller"] not in visited_callers:
                        queue.append((pc["caller"], pc["file_path"], pc["line"], depth + 1))

        return reaching_tests

    def count_totals(self) -> dict[str, int]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(DISTINCT file_path) as total_files FROM symbols")
            tf = cursor.fetchone()["total_files"]
            cursor.execute("SELECT COUNT(*) as total_symbols FROM symbols")
            ts = cursor.fetchone()["total_symbols"]
            cursor.execute("SELECT COUNT(*) as total_calls FROM calls")
            tc = cursor.fetchone()["total_calls"]
            return {"total_files": tf, "total_symbols": ts, "total_calls": tc}
