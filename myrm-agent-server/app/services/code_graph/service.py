"""Code graph service orchestration facade for AST indexing and graph queries.

[INPUT]
- ast_extractor.py::(JsTsRegexExtractor, PythonAstExtractor)
- graph_store.py::CodeGraphStore
- models.py::(IndexStats, ParsedFile)
- myrm_agent_harness.toolkits.filesystem_suggest::WorkspacePathIndexer (POS: git-aware workspace file lister)

[OUTPUT]
- CodeGraphService: 代码图谱业务管理与确定性图遍历服务门面

[POS]
Server 业务服务层。按文件指纹增量同步目录索引（幂等，新增、改动、删除的文件各自处理），提供 7 种确定性图查询。
"""

from __future__ import annotations

import logging
import stat
import time
from pathlib import Path, PurePosixPath

from myrm_agent_harness.toolkits.filesystem_suggest import WorkspacePathIndexer

from app.services.code_graph.ast_extractor import JsTsRegexExtractor, PythonAstExtractor
from app.services.code_graph.graph_store import CodeGraphStore
from app.services.code_graph.models import IndexStats, ParsedFile

logger = logging.getLogger(__name__)

SOURCE_SUFFIXES = frozenset({".py", ".ts", ".tsx", ".js", ".jsx"})
# 超过该大小的源文件基本是生成的打包产物，行扫描既慢又没有导航价值。
MAX_SOURCE_BYTES = 1_000_000


class CodeGraphService:
    """代码调用图谱核心服务：增量索引与 7 种确定性图查询门面。"""

    EXCLUDE_DIRS = frozenset(
        {
            ".git",
            ".venv",
            "node_modules",
            "__pycache__",
            ".next",
            "dist",
            "build",
            ".cursor",
        }
    )

    def __init__(self, db_path: str | Path):
        self.store = CodeGraphStore(db_path)

    def index_directory(self, root_dir: str | Path) -> IndexStats:
        """让索引与目录一致：解析新增与改动的文件，忘掉已删除的文件。

        可反复运行；目录没有变化时只有一次文件列举和每个文件一次 stat。文件清单遵循 git 的忽略规则
        （非 git 目录退回到目录遍历），只按相对扫描根的路径片段排除 ``EXCLUDE_DIRS``，根目录自身的祖先
        目录名不参与判断。符号链接与特殊文件不跟随，超过 ``MAX_SOURCE_BYTES`` 的文件不索引；
        大小与修改时间都没变的改写看不到。
        """
        root = Path(root_dir).expanduser().resolve()
        start_time = time.perf_counter()
        known = self.store.get_file_fingerprints()

        # 列举结果有短时缓存，绕过它，否则刚写入的文件会被漏掉。
        WorkspacePathIndexer.clear_cache(root)
        seen: set[str] = set()
        parsed: list[ParsedFile] = []
        skipped = 0
        for rel_path in WorkspacePathIndexer.list_files(root):
            parts = PurePosixPath(rel_path)
            if parts.suffix not in SOURCE_SUFFIXES or self.EXCLUDE_DIRS.intersection(parts.parts):
                continue
            try:
                info = (root / rel_path).lstat()
            except FileNotFoundError:
                continue  # git 仍在跟踪、但工作区里已经删掉的文件
            except OSError:
                skipped += 1
                continue
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_SOURCE_BYTES:
                skipped += 1
                continue

            seen.add(rel_path)
            fingerprint = (info.st_mtime_ns, info.st_size)
            if known.get(rel_path) == fingerprint:
                continue
            parsed_file = self._parse(root, rel_path, fingerprint)
            if parsed_file is None:
                skipped += 1
            else:
                parsed.append(parsed_file)

        removed = [path for path in known if path not in seen]
        reset = not known
        if parsed or removed or reset:
            self.store.apply_changes(removed=removed, parsed=parsed, reset=reset)

        totals = self.store.count_totals()
        return IndexStats(
            total_files=totals["total_files"],
            total_symbols=totals["total_symbols"],
            total_calls=totals["total_calls"],
            elapsed_ms=(time.perf_counter() - start_time) * 1000.0,
            updated_files=len(parsed),
            removed_files=len(removed),
            skipped_files=skipped,
        )

    @staticmethod
    def _parse(root: Path, rel_path: str, fingerprint: tuple[int, int]) -> ParsedFile | None:
        try:
            code = (root / rel_path).read_text(encoding="utf-8", errors="ignore")
            extractor = PythonAstExtractor(rel_path, code) if rel_path.endswith(".py") else JsTsRegexExtractor(rel_path, code)
            extractor.extract()
        except (OSError, ValueError, RecursionError) as exc:
            logger.warning("Code graph skipped %s: %s", rel_path, exc)
            return None
        return ParsedFile(
            file_path=rel_path,
            mtime_ns=fingerprint[0],
            size=fingerprint[1],
            symbols=extractor.symbols,
            calls=extractor.calls,
            inheritances=extractor.inheritances,
            imports=extractor.imports,
        )

    # ==================== 7 种确定性图查询 ====================

    def resolve(self, target: str, limit: int = 20) -> list[dict[str, object]]:
        """1. 解析符号或 path:line 为完全限定名，最多返回 ``limit`` 条。"""
        return self.store.resolve_names(target, limit)

    def definition(self, qualified_name: str) -> dict[str, object] | None:
        """2. 获取符号的准确定义位置、文档注释与源码。"""
        node = self.store.get_symbol(qualified_name)
        return node.to_dict() if node else None

    def callers(self, callee_name: str) -> list[dict[str, object]]:
        """3. 获取调用指定名称的所有调用点；``match`` 标明是整串相等还是只有最后一段同名。"""
        return self.store.get_callers(callee_name)

    def definition_count(self, name: str) -> int:
        """与 ``name`` 最后一段同名的函数、方法和类的数量，数量大于 1 说明按名字匹配的调用点可能不是同一个函数。"""
        return self.store.count_definitions(name)

    def callees(self, caller_qname: str) -> list[dict[str, object]]:
        """4. 获取指定函数内部的所有调用点（被调用者是调用点上的原文）。"""
        return self.store.get_callees(caller_qname)

    def implementors(self, super_type_name: str) -> list[dict[str, object]]:
        """5. 获取继承或实现指定类/接口的所有派生类型。"""
        return self.store.get_implementors(super_type_name)

    def importers(self, module_name: str) -> list[dict[str, object]]:
        """6. 获取导入了指定模块的所有文件及行号列号。"""
        return self.store.get_importers(module_name)

    def tests_calling(self, target_qname: str) -> list[dict[str, object]]:
        """7. 获取测试文件里直接调用目标的调用点（按名字匹配，不沿调用链继续向上）。"""
        return self.store.get_tests_calling(target_qname)
